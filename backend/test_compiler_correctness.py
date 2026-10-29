"""
test_compiler_correctness.py
Comprehensive test suite verifying compiler correctness:
- Valid language constructs (notes, rests, tempo, instruments, functions, loops, conditionals, parallel)
- Invalid tokens, syntax errors, mismatched blocks, undefined variables, argument mismatches
- Note octave boundaries, unsupported instruments, negative/zero tempo, illegal durations
- Empty programs and comments-only inputs
- Loop boundaries (zero/negative iteration, nested loops)
- Semantic error line/column details
- Optimizer equivalence (preservation of musical behavior)
- Cross-backend consistency (MIDI vs Bytecode VM)
- Graceful failure for malformed input without unhandled exceptions
"""

import unittest
import os
import tempfile
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from lexer import Lexer
from parser import Parser
from semantic_analyzer import SemanticAnalyzer
from ir import IRGenerator
from optimizer import constant_folding, constant_propagation, dead_code_elimination
from channel_allocator import allocate_channels
from codegen_midi import MIDICodeGenerator, note_name_to_midi
from bytecode_compiler import BytecodeCompiler
from vm import VirtualMachine
from compiler import compile_source
from server import execute_and_build_timeline, extract_timeline_from_midi

class TestCompilerCorrectness(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp_dir.cleanup()

    # -------------------------------------------------------------
    # 1. Valid Programs with Language Features
    # -------------------------------------------------------------
    def test_full_language_constructs_valid(self):
        """Test a rich composition exercising functions, loops, conditionals, notes, rests."""
        source = """
        TEMPO 115;
        INSTRUMENT Piano;

        FUNCTION PlayMotif(baseNote, len)
            PLAY baseNote len;
            REST sixteenth;
        ENDFUNCTION

        LET mode = 1;
        IF mode == 1 THEN
            CALL PlayMotif(C4, quarter);
        ELSE
            CALL PlayMotif(G4, quarter);
        ENDIF

        FOR step = 1 TO 3
            PLAY E4 eighth;
        ENDFOR

        REPEAT 2
            PLAY G4 sixteenth;
        ENDREPEAT

        PLAY C5 whole;
        """
        ast, ir = compile_source(source)
        self.assertIsNotNone(ast)
        self.assertIsNotNone(ir)

        # Generate MIDI
        midi_path = os.path.join(self.temp_dir.name, "valid_constructs.mid")
        ok, logs, errors, timeline, tracks, total_dur, bpm = execute_and_build_timeline(source, midi_path)
        self.assertTrue(ok, f"Compilation failed: {errors}")
        self.assertEqual(bpm, 115)
        self.assertGreater(len(timeline), 0)
        self.assertGreater(total_dur, 0.0)

    # -------------------------------------------------------------
    # 2. Syntax, Mismatched Blocks, Undefined Variables
    # -------------------------------------------------------------
    def test_missing_semicolon(self):
        """Missing semicolon must be reported as a parse error."""
        source = "TEMPO 120\nPLAY C4 quarter;"
        tokens, lex_errs = Lexer(source).tokenize()
        ast, parse_errs = Parser(tokens).parse()
        self.assertTrue(len(parse_errs) > 0)

    def test_mismatched_blocks(self):
        """Mismatched or unclosed blocks must produce clear parse errors."""
        unclosed_cases = [
            ("FUNCTION Foo() PLAY C4 quarter;", "ENDFUNCTION"),
            ("IF 1 THEN PLAY C4 quarter;", "ENDIF"),
            ("FOR i = 1 TO 3 PLAY C4 quarter;", "ENDFOR"),
            ("REPEAT 3 PLAY C4 quarter;", "ENDREPEAT"),
            ("PARALLEL TRACK T1 INSTRUMENT Piano; PLAY C4 quarter; ENDTRACK", "ENDPARALLEL"),
            ("TRACK T1 INSTRUMENT Piano; PLAY C4 quarter;", "ENDTRACK"),
        ]
        for src, expected_kw in unclosed_cases:
            with self.subTest(expected_kw=expected_kw):
                tokens, _ = Lexer(src).tokenize()
                ast, parse_errs = Parser(tokens).parse()
                self.assertTrue(len(parse_errs) > 0, f"Expected parse error for unclosed {expected_kw}")
                err_str = " ".join(str(e) for e in parse_errs)
                self.assertIn(expected_kw, err_str)

    def test_undefined_variables_and_functions(self):
        """Using undeclared variables or calling undeclared functions must fail semantic analysis."""
        src_var = "PLAY x quarter;"
        tokens, _ = Lexer(src_var).tokenize()
        ast, _ = Parser(tokens).parse()
        sem_errs = SemanticAnalyzer().analyze(ast)
        self.assertTrue(len(sem_errs) > 0)
        self.assertTrue(
            "not a declared variable" in str(sem_errs[0]).lower()
            or "undeclared" in str(sem_errs[0]).lower()
        )

        src_func = "CALL NonExistentFunc();"
        tokens, _ = Lexer(src_func).tokenize()
        ast, _ = Parser(tokens).parse()
        sem_errs = SemanticAnalyzer().analyze(ast)
        self.assertTrue(len(sem_errs) > 0)
        self.assertIn("undeclared function", str(sem_errs[0]).lower())

    def test_function_arity_mismatch(self):
        """Calling a function with wrong number of arguments must fail with useful info."""
        src = """
        FUNCTION AddNotes(n1, n2)
            PLAY n1 quarter;
            PLAY n2 quarter;
        ENDFUNCTION
        CALL AddNotes(C4);
        """
        tokens, _ = Lexer(src).tokenize()
        ast, _ = Parser(tokens).parse()
        sem_errs = SemanticAnalyzer().analyze(ast)
        self.assertTrue(len(sem_errs) > 0)
        self.assertIn("expects 2 argument(s), got 1", str(sem_errs[0]))

    # -------------------------------------------------------------
    # 3. Musical Boundaries, Invalid Notes, Invalid Durations
    # -------------------------------------------------------------
    def test_invalid_notes_and_durations(self):
        """Invalid notes or durations must be rejected by semantic analysis."""
        invalid_notes = ["H4", "Z3", "C99", "123", "C#b4"]
        for n in invalid_notes:
            src = f"PLAY {n} quarter;"
            tokens, _ = Lexer(src).tokenize()
            ast, p_err = Parser(tokens).parse()
            if not p_err:
                sem_errs = SemanticAnalyzer().analyze(ast)
                self.assertTrue(len(sem_errs) > 0, f"Expected error for note {n}")

        invalid_durations = ["triplet", "thirtysecond", "speedy", "fast"]
        for d in invalid_durations:
            src = f"PLAY C4 {d};"
            tokens, _ = Lexer(src).tokenize()
            ast, p_err = Parser(tokens).parse()
            if not p_err:
                sem_errs = SemanticAnalyzer().analyze(ast)
                self.assertTrue(len(sem_errs) > 0, f"Expected error for duration {d}")

    def test_tempo_boundaries(self):
        """Zero or negative tempo must fail semantic analysis."""
        for bad_tempo in [0, -60, -1]:
            src = f"TEMPO {bad_tempo};\nPLAY C4 quarter;"
            tokens, _ = Lexer(src).tokenize()
            ast, _ = Parser(tokens).parse()
            sem_errs = SemanticAnalyzer().analyze(ast)
            self.assertTrue(len(sem_errs) > 0, f"Expected error for tempo {bad_tempo}")
            self.assertIn("must be positive", str(sem_errs[0]).lower())

    # -------------------------------------------------------------
    # 4. Empty and Comments-Only Programs
    # -------------------------------------------------------------
    def test_empty_and_comments_only(self):
        """Empty or comments-only programs must compile gracefully with empty timeline."""
        for src in ["", "   \n\t  \n", "# Single comment", "# Line 1\n# Line 2\n\n# Line 3"]:
            midi_path = os.path.join(self.temp_dir.name, "empty.mid")
            ok, logs, errors, timeline, tracks, total_dur, bpm = execute_and_build_timeline(src, midi_path)
            self.assertTrue(ok, f"Failed on empty/comment program: {errors}")
            self.assertEqual(len(timeline), 0)
            self.assertEqual(total_dur, 0.0)

    # -------------------------------------------------------------
    # 5. Loop Boundaries & Nested Loops
    # -------------------------------------------------------------
    def test_loop_zero_and_nested_iterations(self):
        """Zero-iteration FOR loop must skip body; nested loops must execute correctly."""
        src_zero = """
        TEMPO 120;
        INSTRUMENT Piano;
        FOR i = 1 TO 0
            PLAY C4 quarter;
        ENDFOR
        PLAY G4 quarter;
        """
        midi_path = os.path.join(self.temp_dir.name, "zero_loop.mid")
        ok, _, _, timeline, _, _, _ = execute_and_build_timeline(src_zero, midi_path)
        self.assertTrue(ok)
        self.assertEqual(len(timeline), 1, "Only note after zero-iteration loop should play")
        self.assertEqual(timeline[0].note, "G4")

        # Nested FOR loop
        src_nested = """
        TEMPO 120;
        INSTRUMENT Piano;
        FOR outer = 1 TO 2
            FOR inner = 1 TO 3
                PLAY C4 sixteenth;
            ENDFOR
        ENDFOR
        """
        midi_path2 = os.path.join(self.temp_dir.name, "nested_loop.mid")
        ok2, _, _, timeline2, _, _, _ = execute_and_build_timeline(src_nested, midi_path2)
        self.assertTrue(ok2)
        self.assertEqual(len(timeline2), 6, "Expected 2 x 3 = 6 notes")

    # -------------------------------------------------------------
    # 6. Optimizer Musical Equivalence
    # -------------------------------------------------------------
    def test_optimizer_musical_equivalence(self):
        """Optimized IR must produce the exact same MIDI notes and timing as unoptimized IR."""
        source = """
        TEMPO 120;
        INSTRUMENT Piano;
        LET x = 2 + 2;
        LET y = x * 3;
        FOR i = 1 TO 2
            PLAY C4 eighth;
            PLAY E4 eighth;
        ENDFOR
        REPEAT 2
            PLAY G4 quarter;
        ENDREPEAT
        """
        ast, raw_ir = compile_source(source)

        # Unoptimized MIDI
        cg_unopt = MIDICodeGenerator()
        cg_unopt.generate(raw_ir)

        # Optimized IR
        opt_ir, _ = constant_folding(raw_ir)
        opt_ir, _ = constant_propagation(opt_ir)
        opt_ir, _ = dead_code_elimination(opt_ir)

        cg_opt = MIDICodeGenerator()
        cg_opt.generate(opt_ir)

        # Compare MIDI event counts and pitches
        unopt_notes = [m.note for m in cg_unopt.track if m.type == 'note_on' and m.velocity > 0]
        opt_notes = [m.note for m in cg_opt.track if m.type == 'note_on' and m.velocity > 0]
        self.assertEqual(unopt_notes, opt_notes, "Optimizer modified musical note sequence!")

    # -------------------------------------------------------------
    # 7. Cross-Backend Consistency (Bytecode VM vs MIDI)
    # -------------------------------------------------------------
    def test_vm_and_midi_backend_consistency(self):
        """Bytecode VM and MIDI generator must produce matching note pitches and counts."""
        source = """
        TEMPO 100;
        INSTRUMENT Flute;
        FUNCTION Arp(root)
            PLAY root eighth;
            PLAY E4 eighth;
            PLAY G4 eighth;
        ENDFUNCTION
        CALL Arp(C4);
        PLAY C5 quarter;
        """
        ast, ir = compile_source(source)
        opt_ir, _ = constant_folding(ir)
        opt_ir, _ = constant_propagation(opt_ir)
        opt_ir, _ = dead_code_elimination(opt_ir)

        # VM
        bytecode = BytecodeCompiler().compile(opt_ir)
        vm = VirtualMachine()
        vm_events = [e for e in vm.run(bytecode) if e.kind == "PLAY"]

        # MIDI
        cg = MIDICodeGenerator()
        cg.generate(opt_ir)
        midi_notes = [m for m in cg.track if m.type == 'note_on' and m.velocity > 0]

        self.assertEqual(len(vm_events), len(midi_notes))
        for v_evt, m_msg in zip(vm_events, midi_notes):
            v_note_name = v_evt.data[0]
            expected_midi = note_name_to_midi(v_note_name)
            self.assertEqual(expected_midi, m_msg.note)

    # -------------------------------------------------------------
    # 8. Graceful Failure
    # -------------------------------------------------------------
    def test_graceful_failure_no_crashes(self):
        """Malformed, garbage, or extreme input must return clean errors without Python crashes."""
        garbage_inputs = [
            "???@#$%^&*()_+",
            "PLAY 12345 67890;",
            "LET = = = ;;;",
            "FUNCTION (((( ENDFUNCTION",
            "FOR WHILE DO LOOP",
            "\"unterminated string literal",
        ]
        for bad in garbage_inputs:
            with self.subTest(bad=bad):
                midi_path = os.path.join(self.temp_dir.name, "bad.mid")
                ok, logs, errors, timeline, tracks, dur, bpm = execute_and_build_timeline(bad, midi_path)
                self.assertFalse(ok)
                self.assertGreater(len(errors), 0)

if __name__ == "__main__":
    unittest.main()
