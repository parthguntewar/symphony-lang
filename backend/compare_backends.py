"""
compare_backends.py
Cross-validation test: compiles a SymphonyLang program, runs it through
BOTH backends (MIDI code generator AND bytecode VM), and checks that they
agree on what music was actually produced.

Why this matters: our compiler produces ONE optimized IR that feeds two
completely independent execution engines (a MIDI event emitter, and a
stack-based VM). If both backends were built correctly from the same IR,
they MUST produce the same sequence of musical events. This script proves
that automatically, instead of us just eyeballing two separate outputs.
"""

from lexer import Lexer
from parser import Parser
from semantic_analyzer import SemanticAnalyzer
from ir import IRGenerator
from optimizer import constant_folding, constant_propagation, dead_code_elimination
from bytecode_compiler import BytecodeCompiler
from vm import VirtualMachine
from codegen_midi import MIDICodeGenerator, note_name_to_midi
from channel_allocator import allocate_channels


def compile_to_ir(source_code):
    """Runs the shared front-end + middle stages: lexer through optimizer."""
    tokens, lex_errors = Lexer(source_code).tokenize()
    if lex_errors:
        return None, None, f"Lex errors: {lex_errors}"

    ast, parse_errors = Parser(tokens).parse()
    if parse_errors:
        return None, None, f"Parse errors: {parse_errors}"

    sem_errors = SemanticAnalyzer().analyze(ast)
    if sem_errors:
        return None, None, f"Semantic errors: {sem_errors}"

    ir = IRGenerator().generate(ast)
    ir, _ = constant_folding(ir)
    ir, _ = constant_propagation(ir)
    ir, _ = dead_code_elimination(ir)
    return ir, ast, None


def run_vm_backend(ir):
    """Returns a simplified list of (kind, data) tuples describing the music."""
    bytecode = BytecodeCompiler().compile(ir)
    events = VirtualMachine().run(bytecode)
    return [(e.kind, e.data) for e in events]


def run_midi_backend(ir, channel_map=None):
    """
    Re-derives the same kind of (kind, data) event list, but this time by
    reading the actual generated MIDI messages - proving the MIDI file
    itself (not just some intermediate step) matches the VM's behavior.
    """
    codegen = MIDICodeGenerator(channel_map=channel_map)
    codegen.generate(ir)
    events = []
    for track in codegen.tracks:
        for msg in track:
            if msg.type == 'set_tempo':
                bpm = round(60_000_000 / msg.tempo)
                events.append(('TEMPO', bpm))
            elif msg.type == 'program_change':
                name = next((k for k, v in
                            __import__('codegen_midi').INSTRUMENT_PROGRAMS.items()
                            if v == msg.program), f"program_{msg.program}")
                events.append(('INSTRUMENT', name))
            elif msg.type == 'note_on':
                events.append(('NOTE_ON', (msg.note, msg.time)))
            elif msg.type == 'note_off':
                events.append(('NOTE_OFF', (msg.note, msg.time)))
    return events



def midi_events_to_note_sequence(midi_events):
    """Extracts just the MIDI note numbers played, in order."""
    return [data[0] for kind, data in midi_events if kind == 'NOTE_ON']

def midi_events_to_note_durations(midi_events):
    """Extracts MIDI note durations in ticks."""
    return [
        data[1]
        for kind, data in midi_events
        if kind == 'NOTE_OFF'
    ]


def vm_events_to_note_sequence(vm_events):
    """Converts the VM's (note_name, duration) PLAY events into MIDI note
    numbers, using the SAME note_name_to_midi() function the MIDI backend
    uses - so we're comparing apples to apples."""
    notes = []
    for kind, data in vm_events:
        if kind == 'PLAY':
            note_name, _duration = data
            notes.append(note_name_to_midi(note_name))
    return notes

def vm_events_to_note_durations(vm_events):
    durations = []
    for kind, data in vm_events:
        if kind == 'PLAY':
            _note, duration = data
            durations.append(duration)
    return durations

def vm_durations_to_ticks(durations, ticks_per_beat=480):
    beats = {
        "whole": 4,
        "half": 2,
        "quarter": 1,
        "eighth": 0.5,
        "sixteenth": 0.25
    }
    return [int(beats[d] * ticks_per_beat) for d in durations]

def compare(source_code, label=""):
    print(f"{'='*60}\nComparing backends for: {label}\n{'='*60}")

    ir, ast, error = compile_to_ir(source_code)
    if error:
        print("Compilation failed:", error)
        return False
    
    channel_map, graph = allocate_channels(ast)

    vm_events = run_vm_backend(ir)
    midi_events = run_midi_backend(ir, channel_map)

    vm_notes = vm_events_to_note_sequence(vm_events)
    midi_notes = midi_events_to_note_sequence(midi_events)
    vm_durations = vm_events_to_note_durations(vm_events)
    midi_durations = midi_events_to_note_durations(midi_events)
    vm_duration_ticks = vm_durations_to_ticks(vm_durations)

    vm_tempo = next((d for k, d in vm_events if k == 'TEMPO'), None)
    midi_tempo = next((d for k, d in midi_events if k == 'TEMPO'), None)

    print("VM   note sequence :", vm_notes)
    print("MIDI note sequence :", midi_notes)
    print("VM   tempo         :", vm_tempo)
    print("MIDI tempo         :", midi_tempo)
    print("VM   durations    :", vm_durations)
    print("MIDI durations   :", midi_durations)
    print("VM   duration ticks:", vm_duration_ticks)

    notes_match = vm_notes == midi_notes
    tempo_match = vm_tempo == midi_tempo
    duration_match = vm_duration_ticks == midi_durations

    if notes_match and tempo_match and duration_match:
        print("\n✅ PASS - both backends produced identical musical output")
        return True
    else:
        print("\n❌ FAIL - backends disagree!")
        if not notes_match:
            print("   Note sequence mismatch")
        if not tempo_match:
            print("   Tempo mismatch")
        if not duration_match:
            print("   Duration mismatch")
        return False


if __name__ == "__main__":
    import sys

    path = sys.argv[1] if len(sys.argv) > 1 else "../testcases/demo_sample.sym"

    with open(path) as f:
        sample = f.read()

    label = path.split("/")[-1]
    
    success = compare(sample, label)
    sys.exit(0 if success else 1)