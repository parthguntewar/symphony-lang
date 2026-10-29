"""
test_instruments.py
Comprehensive automated test suite for the four newly added instruments
(Violin, Flute, Cello, Trumpet), compiler pipeline integration, MIDI generation,
channel allocation, bytecode/VM, and regression verification.
"""

import os
import unittest
import mido

from instruments import (
    INSTRUMENT_PROGRAMS,
    PERCUSSION_INSTRUMENTS,
    VALID_INSTRUMENTS,
    is_valid_instrument,
    canonicalize_instrument,
    get_instrument_program,
    is_percussion,
)
from lexer import Lexer
from parser import Parser
from semantic_analyzer import SemanticAnalyzer
from ir import IRGenerator
from optimizer import constant_folding, constant_propagation, dead_code_elimination
from codegen_midi import MIDICodeGenerator, note_name_to_midi
from bytecode_compiler import BytecodeCompiler
from vm import VirtualMachine
from channel_allocator import allocate_channels, ChannelConflictError
from compare_backends import compare


def compile_pipeline(source_code, channel_map=None):
    """Helper to run the full compiler pipeline and return all intermediate and final artifacts."""
    tokens, lex_errors = Lexer(source_code).tokenize()
    if lex_errors:
        return {"lex_errors": lex_errors}

    ast, parse_errors = Parser(tokens).parse()
    if parse_errors:
        return {"parse_errors": parse_errors, "ast": ast}

    analyzer = SemanticAnalyzer()
    sem_errors = analyzer.analyze(ast)
    if sem_errors:
        return {"sem_errors": sem_errors, "ast": ast}

    ir = IRGenerator().generate(ast)
    ir, _ = constant_folding(ir)
    ir, _ = constant_propagation(ir)
    ir, _ = dead_code_elimination(ir)

    computed_channel_map, graph = allocate_channels(ast)
    active_channel_map = channel_map if channel_map is not None else computed_channel_map

    codegen = MIDICodeGenerator(channel_map=active_channel_map)
    codegen.generate(ir)

    bytecode = BytecodeCompiler().compile(ir)
    vm_events = VirtualMachine().run(bytecode)

    return {
        "ast": ast,
        "ir": ir,
        "channel_map": active_channel_map,
        "codegen": codegen,
        "bytecode": bytecode,
        "vm_events": vm_events,
        "lex_errors": [],
        "parse_errors": [],
        "sem_errors": [],
    }


class TestPhase2InstrumentRegistry(unittest.TestCase):
    """Phase 2: Authoritative instrument registry and exact program mappings."""

    def test_exact_required_program_mappings(self):
        """Verify the exact zero-based General MIDI program numbers requested."""
        self.assertEqual(INSTRUMENT_PROGRAMS["Violin"], 40)
        self.assertEqual(INSTRUMENT_PROGRAMS["Flute"], 73)
        self.assertEqual(INSTRUMENT_PROGRAMS["Cello"], 42)
        self.assertEqual(INSTRUMENT_PROGRAMS["Trumpet"], 56)

    def test_existing_instrument_programs_preserved(self):
        """Verify that existing instrument mappings are preserved without renumbering."""
        self.assertEqual(INSTRUMENT_PROGRAMS["Piano"], 0)
        self.assertEqual(INSTRUMENT_PROGRAMS["Guitar"], 24)
        self.assertEqual(INSTRUMENT_PROGRAMS["Bass"], 32)
        self.assertEqual(INSTRUMENT_PROGRAMS["Clarinet"], 71)
        self.assertEqual(INSTRUMENT_PROGRAMS["Saxophone"], 65)
        self.assertEqual(INSTRUMENT_PROGRAMS["Synth"], 80)
        self.assertEqual(INSTRUMENT_PROGRAMS["Organ"], 19)
        self.assertIn("Drums", PERCUSSION_INSTRUMENTS)

    def test_helper_get_instrument_program(self):
        self.assertEqual(get_instrument_program("Violin"), 40)
        self.assertEqual(get_instrument_program("violin"), 40)
        self.assertEqual(get_instrument_program("VIOLIN"), 40)
        self.assertEqual(get_instrument_program("Flute"), 73)
        self.assertEqual(get_instrument_program("flute"), 73)
        self.assertEqual(get_instrument_program("Cello"), 42)
        self.assertEqual(get_instrument_program("cello"), 42)
        self.assertEqual(get_instrument_program("Trumpet"), 56)
        self.assertEqual(get_instrument_program("trumpet"), 56)

    def test_canonicalize_and_aliases(self):
        self.assertEqual(canonicalize_instrument("violin"), "Violin")
        self.assertEqual(canonicalize_instrument("FLUTE"), "Flute")
        self.assertEqual(canonicalize_instrument("cello"), "Cello")
        self.assertEqual(canonicalize_instrument("Trumpet"), "Trumpet")
        self.assertEqual(canonicalize_instrument("sax"), "Saxophone")
        self.assertEqual(canonicalize_instrument("drum"), "Drums")
        self.assertEqual(canonicalize_instrument("percussion"), "Drums")

    def test_percussion_handling(self):
        self.assertTrue(is_percussion("Drums"))
        self.assertTrue(is_percussion("drums"))
        self.assertTrue(is_percussion("percussion"))
        self.assertFalse(is_percussion("Violin"))
        with self.assertRaises(ValueError):
            get_instrument_program("Drums")

    def test_unsupported_instrument_in_registry(self):
        self.assertFalse(is_valid_instrument("Tuba"))
        self.assertFalse(is_valid_instrument("Banjo"))
        self.assertFalse(is_valid_instrument("Accordion"))
        with self.assertRaises(ValueError):
            get_instrument_program("Banjo")


class TestPhase3CompilerPipeline(unittest.TestCase):
    """Phase 3: Lexer, Parser, Semantic Analyzer, IR, Optimizer pipeline."""

    def test_individual_instruments(self):
        for name in ("Violin", "Flute", "Cello", "Trumpet"):
            src = f"TEMPO 120;\nINSTRUMENT {name};\nPLAY C4 quarter;\n"
            res = compile_pipeline(src)
            self.assertEqual(res.get("lex_errors"), [], f"Lex error for {name}")
            self.assertEqual(res.get("parse_errors"), [], f"Parse error for {name}")
            self.assertEqual(res.get("sem_errors"), [], f"Semantic error for {name}")
            ir_instrs = res["ir"]
            instrument_ir = [i for i in ir_instrs if i.opcode == "INSTRUMENT"]
            self.assertEqual(len(instrument_ir), 1)
            self.assertEqual(instrument_ir[0].args[0], name)

    def test_case_insensitive_declarations(self):
        for raw, expected in (
            ("violin", "Violin"),
            ("FLUTE", "Flute"),
            ("Cello", "Cello"),
            ("trumpet", "Trumpet"),
        ):
            src = f"INSTRUMENT {raw};\nPLAY C4 quarter;\n"
            res = compile_pipeline(src)
            self.assertEqual(res.get("sem_errors"), [])
            instrument_ir = [i for i in res["ir"] if i.opcode == "INSTRUMENT"]
            self.assertEqual(instrument_ir[0].args[0], expected)

    def test_invalid_instrument_rejection(self):
        src = "INSTRUMENT Banjo;\nPLAY C4 quarter;\n"
        tokens, _ = Lexer(src).tokenize()
        ast, _ = Parser(tokens).parse()
        errors = SemanticAnalyzer().analyze(ast)
        self.assertTrue(len(errors) > 0)
        self.assertIn("Unknown instrument 'Banjo'", str(errors[0]))

    def test_malformed_instrument_declarations(self):
        src1 = "INSTRUMENT;"
        tokens1, _ = Lexer(src1).tokenize()
        _, parse_errors1 = Parser(tokens1).parse()
        self.assertTrue(len(parse_errors1) > 0)

        src2 = "INSTRUMENT Violin"  # missing semicolon
        tokens2, _ = Lexer(src2).tokenize()
        _, parse_errors2 = Parser(tokens2).parse()
        self.assertTrue(len(parse_errors2) > 0)


class TestPhase4MIDIBackend(unittest.TestCase):
    """Phase 4: MIDI backend generation, program changes, channels, timing."""

    def test_midi_program_change_values(self):
        cases = {
            "Violin": 40,
            "Flute": 73,
            "Cello": 42,
            "Trumpet": 56,
        }
        for name, expected_prog in cases.items():
            src = f"INSTRUMENT {name};\nPLAY C4 quarter;\n"
            res = compile_pipeline(src)
            codegen = res["codegen"]
            prog_changes = [m for m in codegen.tracks[0] if m.type == "program_change"]
            self.assertTrue(len(prog_changes) >= 1)
            self.assertEqual(prog_changes[0].program, expected_prog)
            self.assertEqual(prog_changes[0].channel, 0)

    def test_program_change_precedes_notes(self):
        src = "INSTRUMENT Violin;\nPLAY C4 quarter;\n"
        res = compile_pipeline(src)
        track = res["codegen"].tracks[0]
        pc_idx = next(i for i, m in enumerate(track) if m.type == "program_change")
        note_on_idx = next(i for i, m in enumerate(track) if m.type == "note_on")
        self.assertLess(pc_idx, note_on_idx)

    def test_mid_stream_instrument_change(self):
        src = """
        INSTRUMENT Violin;
        PLAY C4 quarter;
        INSTRUMENT Trumpet;
        PLAY D4 quarter;
        """
        res = compile_pipeline(src)
        track = res["codegen"].tracks[0]
        pc_msgs = [m for m in track if m.type == "program_change"]
        self.assertEqual(len(pc_msgs), 2)
        self.assertEqual(pc_msgs[0].program, 40)
        self.assertEqual(pc_msgs[1].program, 56)

    def test_no_silent_fallback_to_piano_on_unsupported(self):
        codegen = MIDICodeGenerator()
        with self.assertRaises(ValueError):
            codegen._emit_instrument("UnsupportedInstrumentXYZ")

    def test_multi_track_simultaneous_instruments(self):
        src = """
        PARALLEL
            TRACK ViolinTrack
                INSTRUMENT Violin;
                PLAY C4 quarter;
            ENDTRACK
            TRACK FluteTrack
                INSTRUMENT Flute;
                PLAY E4 quarter;
            ENDTRACK
            TRACK CelloTrack
                INSTRUMENT Cello;
                PLAY G3 quarter;
            ENDTRACK
            TRACK TrumpetTrack
                INSTRUMENT Trumpet;
                PLAY C5 quarter;
            ENDTRACK
        ENDPARALLEL
        """
        res = compile_pipeline(src)
        codegen = res["codegen"]
        self.assertEqual(len(codegen.tracks), 5)  # track 0 + 4 parallel tracks

        expected = [
            ("ViolinTrack", 40, 60),
            ("FluteTrack", 73, 64),
            ("CelloTrack", 42, 55),
            ("TrumpetTrack", 56, 72),
        ]
        assigned_channels = set()
        for idx, (tname, expected_prog, expected_note) in enumerate(expected, start=1):
            t = codegen.tracks[idx]
            pcs = [m for m in t if m.type == "program_change"]
            notes = [m for m in t if m.type == "note_on"]
            self.assertEqual(len(pcs), 1, f"Missing program change on {tname}")
            self.assertEqual(pcs[0].program, expected_prog)
            self.assertEqual(notes[0].note, expected_note)
            self.assertEqual(pcs[0].channel, notes[0].channel)
            assigned_channels.add(pcs[0].channel)

        # Confirm all 4 tracks got distinct channels
        self.assertEqual(len(assigned_channels), 4)

    def test_generated_midi_file_validity(self):
        src = """
        TEMPO 120;
        INSTRUMENT Flute;
        PLAY G4 quarter;
        """
        res = compile_pipeline(src)
        tmp_path = "test_flute_valid.mid"
        try:
            res["codegen"].save(tmp_path)
            mid = mido.MidiFile(tmp_path)
            self.assertGreater(len(mid.tracks), 0)
            all_types = [m.type for tr in mid.tracks for m in tr]
            self.assertIn("set_tempo", all_types)
            self.assertIn("program_change", all_types)
            self.assertIn("note_on", all_types)
            self.assertIn("note_off", all_types)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)


class TestPhase5ChannelAllocation(unittest.TestCase):
    """Phase 5: MIDI channel allocation, graph coloring, drums, exhaustion."""

    def test_parallel_conflict_free_channels(self):
        src = """
        PARALLEL
            TRACK T1
                INSTRUMENT Violin;
                PLAY C4 quarter;
            ENDTRACK
            TRACK T2
                INSTRUMENT Flute;
                PLAY D4 quarter;
            ENDTRACK
            TRACK T3
                INSTRUMENT Cello;
                PLAY E4 quarter;
            ENDTRACK
            TRACK T4
                INSTRUMENT Trumpet;
                PLAY F4 quarter;
            ENDTRACK
        ENDPARALLEL
        """
        tokens, _ = Lexer(src).tokenize()
        ast, _ = Parser(tokens).parse()
        ch_map, graph = allocate_channels(ast)
        channels = [ch_map[t] for t in ("T1", "T2", "T3", "T4")]
        self.assertEqual(len(set(channels)), 4)
        for c in channels:
            self.assertNotEqual(c, 9)

    def test_drums_pinned_to_channel_9(self):
        src = """
        PARALLEL
            TRACK ViolinTrack
                INSTRUMENT Violin;
                PLAY C4 quarter;
            ENDTRACK
            TRACK Drums
                PLAY C1 quarter;
            ENDTRACK
        ENDPARALLEL
        """
        tokens, _ = Lexer(src).tokenize()
        ast, _ = Parser(tokens).parse()
        ch_map, _ = allocate_channels(ast)
        self.assertEqual(ch_map["Drums"], 9)
        self.assertNotEqual(ch_map["ViolinTrack"], 9)

    def test_drums_via_instrument_statement_pinned_to_channel_9(self):
        src = """
        PARALLEL
            TRACK Percussion
                INSTRUMENT Drums;
                PLAY C1 quarter;
            ENDTRACK
            TRACK FluteTrack
                INSTRUMENT Flute;
                PLAY E4 quarter;
            ENDTRACK
        ENDPARALLEL
        """
        tokens, _ = Lexer(src).tokenize()
        ast, _ = Parser(tokens).parse()
        ch_map, _ = allocate_channels(ast)
        self.assertEqual(ch_map["Percussion"], 9)
        self.assertNotEqual(ch_map["FluteTrack"], 9)

    def test_channel_exhaustion_raises_error(self):
        # 16 simultaneous melodic tracks exceeds 15 available channels
        track_defs = "\n".join(
            f"TRACK T{i}\n    PLAY C4 quarter;\nENDTRACK" for i in range(16)
        )
        src = f"PARALLEL\n{track_defs}\nENDPARALLEL"
        tokens, _ = Lexer(src).tokenize()
        ast, _ = Parser(tokens).parse()
        with self.assertRaises(ChannelConflictError):
            allocate_channels(ast)


class TestPhase6BytecodeAndVM(unittest.TestCase):
    """Phase 6: Bytecode compiler and VM preserving instrument identities."""

    def test_bytecode_and_vm_all_four_instruments(self):
        for name in ("Violin", "Flute", "Cello", "Trumpet"):
            src = f"INSTRUMENT {name};\nPLAY C4 quarter;\n"
            res = compile_pipeline(src)
            bytecode = res["bytecode"]
            vm_events = res["vm_events"]

            # Bytecode verification
            instr_opcodes = [b for b in bytecode if b.opcode == "INSTR"]
            self.assertEqual(len(instr_opcodes), 1)
            self.assertEqual(instr_opcodes[0].operand, name)

            # VM events verification
            inst_events = [e for e in vm_events if e.kind == "INSTRUMENT"]
            self.assertEqual(len(inst_events), 1)
            self.assertEqual(inst_events[0].data, name)

    def test_bytecode_and_vm_multitrack_preservation(self):
        src = """
        PARALLEL
            TRACK ViolinTrack
                INSTRUMENT Violin;
                PLAY C4 quarter;
            ENDTRACK
            TRACK CelloTrack
                INSTRUMENT Cello;
                PLAY C3 quarter;
            ENDTRACK
        ENDPARALLEL
        """
        res = compile_pipeline(src)
        bytecode = res["bytecode"]
        vm_events = res["vm_events"]

        # Bytecode contains TRACK and ENDTRACK
        track_opcodes = [b.opcode for b in bytecode if b.opcode in ("TRACK", "ENDTRACK", "INSTR")]
        self.assertIn("TRACK", track_opcodes)
        self.assertIn("ENDTRACK", track_opcodes)
        self.assertIn("INSTR", track_opcodes)

        # VM events contain tracks and instruments
        kinds = [e.kind for e in vm_events]
        self.assertIn("TRACK", kinds)
        self.assertIn("INSTRUMENT", kinds)
        self.assertIn("ENDTRACK", kinds)

        inst_events = [e.data for e in vm_events if e.kind == "INSTRUMENT"]
        self.assertIn("Violin", inst_events)
        self.assertIn("Cello", inst_events)

    def test_cross_backend_comparison(self):
        for inst in ("Violin", "Flute", "Cello", "Trumpet"):
            src = f"""
            TEMPO 120;
            INSTRUMENT {inst};
            PLAY C4 quarter;
            PLAY D4 quarter;
            """
            success = compare(src, f"test_{inst}")
            self.assertTrue(success, f"Backends disagreed for {inst}")


class TestPhase7Regression(unittest.TestCase):
    """Phase 7: Full regression across all existing examples."""

    def test_all_existing_testcases_compile(self):
        import glob
        test_files = sorted(glob.glob("../testcases/*.sym") + glob.glob("../testcases/regression/*.sym"))
        self.assertGreater(len(test_files), 0)
        for path in test_files:
            with open(path) as f:
                content = f.read()
            res = compile_pipeline(content)
            self.assertEqual(res.get("lex_errors", []), [], f"Lex error in {path}")
            self.assertEqual(res.get("parse_errors", []), [], f"Parse error in {path}")
            self.assertEqual(res.get("sem_errors", []), [], f"Semantic error in {path}")
            self.assertIsNotNone(res.get("codegen"), f"Codegen failed for {path}")


if __name__ == "__main__":
    unittest.main()
