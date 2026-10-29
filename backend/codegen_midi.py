"""
codegen_midi.py
The final stage of the compiler: takes the (optimized) IR instruction list
and produces an actual, playable .mid file.

Unlike earlier stages, this one actually EXECUTES the IR:
    - follows GOTO / IF_FALSE jumps to correctly run loops
    - handles CALL / RETURN to correctly run function calls
    - tracks variable values as the "program" runs

Whenever it executes a PLAY, REST, TEMPO, or INSTRUMENT instruction,
it emits the corresponding real MIDI event.

NOTE ON SCOPE (v1): this backend uses a single MIDI track/channel
(except DRUMS, which uses the standard percussion channel 9).
Multi-track / multi-channel support with conflict-free channel
assignment is a planned addition (channel allocator - a register-
allocation-style optimization pass), not implemented in this version.
"""

import re
import mido
from channel_allocator import allocate_channels
from mido import Message, MetaMessage, MidiFile, MidiTrack, bpm2tempo

NOTE_PATTERN = re.compile(r"^[A-G](#|b)?\d$")
DURATIONS = {"whole", "half", "quarter", "eighth", "sixteenth"}

NOTE_BASE = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}

# General MIDI program numbers (0-indexed) for supported instruments.
from instruments import (
    INSTRUMENT_PROGRAMS,
    PERCUSSION_INSTRUMENTS,
    VALID_INSTRUMENTS,
    is_valid_instrument,
    canonicalize_instrument,
    get_instrument_program,
    is_percussion,
)

ARITH_OPS = {
    'ADD': lambda a, b: a + b, 'SUB': lambda a, b: a - b,
    'MUL': lambda a, b: a * b, 'DIV': lambda a, b: a // b if b != 0 else 0,
}
COMPARE_OPS = {
    'LT': lambda a, b: a < b, 'GT': lambda a, b: a > b,
    'LE': lambda a, b: a <= b, 'GE': lambda a, b: a >= b,
    'EQ': lambda a, b: a == b, 'NE': lambda a, b: a != b,
}


def note_name_to_midi(note):
    """Converts a note like 'C4' or 'D#5' or 'Bb3' into a MIDI note number (0-127).
    Formula: (octave + 1) * 12 + base_semitone + accidental."""
    m = re.match(r"^([A-G])([#b]?)(\d)$", note)
    if not m:
        raise ValueError(f"Invalid note format: {note}")
    letter, accidental, octave = m.group(1), m.group(2), int(m.group(3))
    value = (octave + 1) * 12 + NOTE_BASE[letter]
    if accidental == '#':
        value += 1
    elif accidental == 'b':
        value -= 1
    return max(0, min(127, value))


class MIDICodeGenerator:
    def __init__(self, ticks_per_beat=480, channel_map=None):
        self.ticks_per_beat = ticks_per_beat
        self.channel_map = channel_map or {}
        self.track = MidiTrack()
        self.tracks = [self.track]
        self.pending_delay = 0
        self.channel = 0
        self.current_track_name = None
        self.track_states = {}
        self.max_steps = 200_000

    # ---------- timing helpers ----------

    def _duration_ticks(self, duration_word):
        beats = {"whole": 4, "half": 2, "quarter": 1,
                 "eighth": 0.5, "sixteenth": 0.25}[duration_word]
        return int(beats * self.ticks_per_beat)

    def _select_track(self, name, channel=None):
        if name not in self.track_states:
            track = MidiTrack()
            self.tracks.append(track)
            if channel is not None:
                assigned_channel = channel
            elif name in self.channel_map:
                assigned_channel = self.channel_map[name]
            elif is_percussion(name):
                assigned_channel = 9
            else:
                used_channels = {st["channel"] for st in self.track_states.values()}
                assigned_channel = next(
                    (c for c in range(16) if c != 9 and c not in used_channels), 0
                )

            self.track_states[name] = {
                "track": track,
                "channel": assigned_channel,
                "pending_delay": 0,
                "instrument": None,
            }
        state = self.track_states[name]
        self.current_track_name = name
        self.track = state["track"]
        self.channel = state["channel"]
        self.pending_delay = state["pending_delay"]

        if state.get("instrument") is None and is_valid_instrument(name):
            self._emit_instrument(name)

    def _sync_track_state(self):
        if self.current_track_name is not None:
            state = self.track_states[self.current_track_name]
            state["channel"] = self.channel
            state["pending_delay"] = self.pending_delay

    # ---------- MIDI emission ----------

    def _emit_note(self, note_str, duration_word):
        ticks = self._duration_ticks(duration_word)
        midi_num = note_name_to_midi(note_str)
        self.track.append(
            Message(
                'note_on',
                channel=self.channel,
                note=midi_num,
                velocity=80,
                time=self.pending_delay
            )
        )
        
        self.pending_delay = 0
        self.track.append(
            Message(
                'note_off',
                channel=self.channel,
                note=midi_num,
                velocity=80,
                time=ticks
            )
        )
        self._sync_track_state()

    def _emit_rest(self, duration_word):
        self.pending_delay += self._duration_ticks(duration_word)
        self._sync_track_state()

    def _emit_tempo(self, bpm):
        self.track.append(
            MetaMessage(
                'set_tempo',
                tempo=bpm2tempo(bpm),
                time=self.pending_delay
            )
        )
        self.pending_delay = 0
        self._sync_track_state()

    def _emit_instrument(self, name):
        if not is_valid_instrument(name):
            raise ValueError(
                f"Unknown instrument '{name}'. Cannot emit MIDI program change. "
                f"Valid options: {', '.join(sorted(VALID_INSTRUMENTS))}"
            )

        canonical = canonicalize_instrument(name)
        if is_percussion(canonical):
            self.channel = 9
            if self.current_track_name is not None:
                self.track_states[self.current_track_name]["instrument"] = canonical
            self._sync_track_state()
            return

        self.channel = 0 if self.current_track_name is None else self.channel
        program = INSTRUMENT_PROGRAMS[canonical]

        # Avoid redundant duplicate program change if already set at this time
        if self.current_track_name is not None and self.track_states[self.current_track_name].get("instrument") == canonical:
            if self.pending_delay == 0 and len(self.track) > 0 and self.track[-1].type == 'program_change' and self.track[-1].program == program:
                return

        self.track.append(
            Message(
                'program_change',
                channel=self.channel,
                program=program,
                time=self.pending_delay
            )
        )
        self.pending_delay = 0
        if self.current_track_name is not None:
            self.track_states[self.current_track_name]["instrument"] = canonical
        self._sync_track_state()

    # ---------- IR interpretation ----------

    def generate(self, instructions):
        label_map = {}
        func_map = {}
        for i, instr in enumerate(instructions):
            if instr.opcode == 'LABEL':
                label_map[instr.args[0]] = i
            elif instr.opcode == 'FUNC_BEGIN':
                name = instr.args[0]
                params = instr.args[1:]
                func_map[name] = {'params': params, 'start': i + 1}
            elif instr.opcode == 'FUNC_END':
                name = instr.args[0]
                func_map[name]['end'] = i

        env_stack = [{}]
        return_stack = []
        param_queue = []

        def resolve(x):
            if isinstance(x, (int, float)):
                return x
            for scope in reversed(env_stack):
                if x in scope:
                    return scope[x]
            return x  # not a known variable - treat as a literal string (note/duration)

        pc = 0
        steps = 0
        while pc < len(instructions):
            steps += 1
            if steps > self.max_steps:
                raise RuntimeError("Execution exceeded max step limit - possible infinite loop")

            instr = instructions[pc]
            op = instr.opcode

            if op in ('LABEL', 'INCLUDE'):
                pc += 1

            elif op == 'TRACK_BEGIN':
                track_name = instr.args[0]
                self._select_track(track_name)
                pc += 1

            elif op == 'TRACK_END':
                self._sync_track_state()

                self.current_track_name = None
                self.track = self.tracks[0]
                self.channel = 0
                self.pending_delay = 0
                pc += 1

            elif op == 'ASSIGN':
                env_stack[-1][instr.result] = resolve(instr.args[0])
                pc += 1

            elif op in ARITH_OPS:
                a, b = resolve(instr.args[0]), resolve(instr.args[1])
                env_stack[-1][instr.result] = ARITH_OPS[op](a, b)
                pc += 1

            elif op in COMPARE_OPS:
                a, b = resolve(instr.args[0]), resolve(instr.args[1])
                env_stack[-1][instr.result] = COMPARE_OPS[op](a, b)
                pc += 1

            elif op == 'NEG':
                env_stack[-1][instr.result] = -resolve(instr.args[0])
                pc += 1

            elif op == 'GOTO':
                pc = label_map[instr.args[0]]

            elif op == 'IF_FALSE':
                cond = resolve(instr.args[0])
                pc = label_map[instr.args[1]] if not cond else pc + 1

            elif op == 'PLAY':
                note_raw, dur_raw = instr.args
                note = note_raw if NOTE_PATTERN.match(str(note_raw)) else str(resolve(note_raw))
                dur = dur_raw if dur_raw in DURATIONS else str(resolve(dur_raw))
                self._emit_note(note, dur)
                pc += 1

            elif op == 'REST':
                dur_raw = instr.args[0]
                dur = dur_raw if dur_raw in DURATIONS else str(resolve(dur_raw))
                self._emit_rest(dur)
                pc += 1

            elif op == 'TEMPO':
                self._emit_tempo(resolve(instr.args[0]))
                pc += 1

            elif op == 'INSTRUMENT':
                self._emit_instrument(instr.args[0])
                pc += 1

            elif op == 'PARAM':
                param_queue.append(resolve(instr.args[0]))
                pc += 1

            elif op == 'CALL':
                fname, nargs = instr.args
                arg_vals = param_queue[len(param_queue) - nargs:] if nargs > 0 else []
                del param_queue[len(param_queue) - nargs:]
                finfo = func_map[fname]
                new_scope = dict(zip(finfo['params'], arg_vals))
                env_stack.append(new_scope)
                return_stack.append(pc + 1)
                pc = finfo['start']

            elif op == 'RETURN':
                env_stack.pop()
                pc = return_stack.pop()

            elif op == 'FUNC_END':
                # Reached without an explicit RETURN inside the function -
                # treat it as an implicit "return with no value".
                if return_stack:
                    env_stack.pop()
                    pc = return_stack.pop()
                else:
                    # Should not normally happen (IR always GOTOs around
                    # function bodies at the top level), but guard anyway.
                    pc += 1

            elif op == 'FUNC_BEGIN':
                # Only reached via fall-through if a function has no RETURN -
                # treat reaching FUNC_END the same way (handled above).
                pc += 1

            else:
                pc += 1  # unknown opcode - skip safely

        return self.track

    def save(self, path):
        mid = MidiFile(ticks_per_beat=self.ticks_per_beat)
        for track in self.tracks:
            mid.tracks.append(track)
        mid.save(path)
        return path


if __name__ == "__main__":
    from lexer import Lexer
    from parser import Parser
    from ir import IRGenerator, print_ir
    from optimizer import constant_folding, constant_propagation, dead_code_elimination

    sample = """
TEMPO 100;
INSTRUMENT Piano;

PLAY C4 quarter;
PLAY E4 quarter;
PLAY G4 quarter;
PLAY C5 half;
PLAY G4 quarter;
PLAY E4 quarter;
PLAY C4 whole;    
"""

    tokens, lex_errors = Lexer(sample).tokenize()
    ast, parse_errors = Parser(tokens).parse()
    print("Parse errors:", parse_errors)

    ir = IRGenerator().generate(ast)
    ir, _ = constant_folding(ir)
    ir, _ = constant_propagation(ir)
    ir, _ = dead_code_elimination(ir)

    print("\nFinal IR:")
    print_ir(ir)

    codegen = MIDICodeGenerator()
    codegen.generate(ir)
    out_path = codegen.save("output.mid")
    print(f"\nSaved MIDI file to: {out_path}")

    # Sanity check: read it back and show the messages.
    mid = mido.MidiFile(out_path)
    print(f"\nMIDI file has {len(mid.tracks[0])} messages, "
          f"ticks_per_beat={mid.ticks_per_beat}")
    for msg in mid.tracks[0]:
        print(" ", msg)