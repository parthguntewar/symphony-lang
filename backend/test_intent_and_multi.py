"""
test_intent_and_multi.py
Automated test suite verifying:
- Scenario A: Intent handling for greetings ("hi", "hello", "hey", "thanks")
- Scenario B: Intent handling for unrelated queries (redirecting politely without generating music)
- Scenario C: Single-instrument music generation and compilation
- Scenario D: 5-instrument simultaneous orchestral generation (all instruments start at t=0s, overlap, distinct roles, valid MIDI)
- Scenario E: Unsupported instrument diagnosis and user guidance
- Scenario F: Modification of previous compositions (e.g. tempo change, instrument change)
"""

import unittest
import os
import tempfile
from pathlib import Path
import sys

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from composer import (
    process_user_intent_and_compose,
    is_greeting,
    is_unrelated_query,
    detect_instruments,
    extract_tempo,
)
from instruments import VALID_INSTRUMENTS
from server import execute_and_build_timeline, extract_timeline_from_midi
from compiler import compile_source

class TestIntentAndMultiInstrument(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp_dir.cleanup()

    # -------------------------------------------------------------
    # Scenario A: Greetings
    # -------------------------------------------------------------
    def test_greeting_handling(self):
        """Entering 'hi', 'hello', 'hey', 'thanks' must not generate music."""
        greetings = [
            "hi",
            "hello",
            "Hey there!",
            "good morning",
            "thanks for your help",
            "thank you!",
        ]
        for prompt in greetings:
            with self.subTest(prompt=prompt):
                self.assertTrue(is_greeting(prompt), f"Failed to identify greeting: {prompt}")
                code, explanation, is_comp, is_template = process_user_intent_and_compose(prompt)
                self.assertFalse(is_comp, f"Greeting '{prompt}' should not trigger composition")
                self.assertIsNone(code, f"Greeting '{prompt}' should not produce code")
                self.assertIn("SymphonyLang", explanation)
                self.assertIn("describe", explanation.lower())

    # -------------------------------------------------------------
    # Scenario B: Unrelated questions
    # -------------------------------------------------------------
    def test_unrelated_questions_redirection(self):
        """Unrelated non-music questions must be politely redirected without generating music."""
        unrelated_prompts = [
            "What is the capital of France?",
            "Write a Python script to scrape a website.",
            "Who was the first president of the United States?",
            "Can you solve 2 + 2?",
            "What is quantum computing?",
        ]
        for prompt in unrelated_prompts:
            with self.subTest(prompt=prompt):
                self.assertTrue(is_unrelated_query(prompt), f"Failed to identify unrelated: {prompt}")
                code, explanation, is_comp, is_template = process_user_intent_and_compose(prompt)
                self.assertFalse(is_comp, f"Unrelated prompt '{prompt}' should not trigger composition")
                self.assertIsNone(code, f"Unrelated prompt '{prompt}' should not produce code")
                self.assertIn("specialized", explanation.lower())
                self.assertIn("music", explanation.lower())

    # -------------------------------------------------------------
    # Scenario C: Single-instrument composition
    # -------------------------------------------------------------
    def test_single_instrument_composition(self):
        """A prompt requesting a cheerful piano melody generates valid single-track code."""
        prompt = "Create a cheerful piano melody at 110 BPM."
        code, explanation, is_comp, is_template = process_user_intent_and_compose(prompt)
        self.assertTrue(is_comp)
        self.assertIsNotNone(code)
        self.assertIn("TEMPO 110;", code)
        self.assertIn("INSTRUMENT Piano;", code)
        self.assertIn("PLAY", code)

        # Verify compilation and timeline
        midi_path = os.path.join(self.temp_dir.name, "single_piano.mid")
        ok, logs, errors, timeline, tracks, total_dur, bpm = execute_and_build_timeline(code, midi_path)
        self.assertTrue(ok, f"Compilation failed: {errors}")
        self.assertGreater(len(timeline), 0)
        self.assertEqual(bpm, 110)
        insts = {e.instrument for e in timeline}
        self.assertIn("Piano", insts)

    # -------------------------------------------------------------
    # Scenario D: 5-instrument simultaneous orchestral composition
    # -------------------------------------------------------------
    def test_five_instrument_parallel_orchestral_composition(self):
        """
        Verify that requesting 5 simultaneous instruments (Piano, Violin, Flute, Cello, Trumpet)
        at 100 BPM generates a valid PARALLEL composition where all 5 instruments start at beat 0,
        have distinct registers/roles, overlap, and compile into a valid MIDI file.
        """
        prompt = (
            "Create a cinematic orchestral composition at 100 BPM using five simultaneous instruments: "
            "Piano, Violin, Flute, Cello, and Trumpet. All five instruments must start at beat zero, "
            "have distinct musical roles, overlap throughout the composition, and produce a valid MIDI file."
        )
        code, explanation, is_comp, is_template = process_user_intent_and_compose(prompt)
        self.assertTrue(is_comp)
        self.assertIsNotNone(code)

        # Check code structure
        self.assertIn("TEMPO 100;", code)
        self.assertIn("PARALLEL", code)
        self.assertIn("ENDPARALLEL", code)

        for inst in ["Piano", "Violin", "Flute", "Cello", "Trumpet"]:
            self.assertIn(f"INSTRUMENT {inst};", code, f"Missing instrument {inst} in generated code")

        # Compile and generate MIDI
        midi_path = os.path.join(self.temp_dir.name, "quintet_cinematic.mid")
        ok, logs, errors, timeline, tracks, total_dur, bpm = execute_and_build_timeline(code, midi_path)
        self.assertTrue(ok, f"Compilation failed: {errors}")

        # Verify all 5 instruments are present in the compiled timeline events
        insts_in_timeline = {e.instrument for e in timeline}
        for inst in ["Piano", "Violin", "Flute", "Cello", "Trumpet"]:
            self.assertIn(inst, insts_in_timeline, f"Instrument {inst} not found in timeline: {insts_in_timeline}")

        # Verify that all 5 instruments have notes starting at t = 0.0s (beat 0)
        start_zero_instruments = set()
        for evt in timeline:
            if abs(evt.start_sec) < 0.001:
                start_zero_instruments.add(evt.instrument)

        expected_five = {"Piano", "Violin", "Flute", "Cello", "Trumpet"}
        self.assertEqual(
            start_zero_instruments,
            expected_five,
            f"Expected all 5 instruments to start at t=0, but got: {start_zero_instruments}"
        )

        # Verify polyphonic overlap: check that multiple notes from different instruments play simultaneously
        time_buckets = {}
        for evt in timeline:
            t = round(evt.start_sec, 2)
            time_buckets.setdefault(t, set()).add(evt.instrument)

        # Check that there are time points where all 5 instruments are playing together
        simultaneous_inst_counts = [len(insts) for insts in time_buckets.values()]
        max_simultaneous = max(simultaneous_inst_counts)
        self.assertGreaterEqual(
            max_simultaneous, 5,
            f"Expected at least 5 simultaneous instruments, max observed was {max_simultaneous}"
        )

        # Verify total duration is positive and tempo is 100 BPM
        self.assertGreater(total_dur, 2.0)
        self.assertEqual(bpm, 100)

    # -------------------------------------------------------------
    # Scenario E: Unsupported instrument diagnosis
    # -------------------------------------------------------------
    def test_unsupported_instrument_handling(self):
        """Requesting unsupported instruments (e.g. Harp, Tuba, Sitar) provides clear guidance."""
        prompt = "Play an energetic solo on harp and accordion at 130 BPM."
        code, explanation, is_comp, is_template = process_user_intent_and_compose(prompt)
        self.assertFalse(is_comp)
        self.assertIsNone(code)
        self.assertIn("unsupported instrument", explanation.lower())
        self.assertIn("harp", explanation.lower())
        self.assertIn("accordion", explanation.lower())
        for supported in ["Piano", "Violin", "Flute", "Cello", "Trumpet", "Guitar"]:
            self.assertIn(supported, explanation)

    # -------------------------------------------------------------
    # Scenario F: Modification of previous composition
    # -------------------------------------------------------------
    def test_modification_handling(self):
        """User requests changes to tempo or instruments for an existing composition."""
        previous_code = """TEMPO 100;
TRACK PianoTrack
    INSTRUMENT Piano;
    PLAY C4 quarter;
    PLAY E4 quarter;
    PLAY G4 half;
ENDTRACK
"""
        # Test tempo change
        mod_prompt = "Make it faster, set tempo to 150 BPM."
        new_code, explanation, is_comp, is_template = process_user_intent_and_compose(
            mod_prompt, previous_code=previous_code
        )
        self.assertTrue(is_comp)
        self.assertIsNotNone(new_code)
        self.assertIn("TEMPO 150;", new_code)
        self.assertIn("Piano", new_code)

        # Test instrument change
        mod_inst_prompt = "Change the instrument to Flute."
        new_code2, _, is_comp2, _ = process_user_intent_and_compose(
            mod_inst_prompt, previous_code=previous_code
        )
        self.assertTrue(is_comp2)
        self.assertIsNotNone(new_code2)
        self.assertIn("Flute", new_code2)

        # Test adding an instrument track
        add_track_prompt = "Add a bass track."
        new_code3, exp3, is_comp3, _ = process_user_intent_and_compose(
            add_track_prompt, previous_code=previous_code
        )
        self.assertTrue(is_comp3)
        self.assertIsNotNone(new_code3)
        self.assertIn("Bass", new_code3)
        self.assertIn("PARALLEL", new_code3)

        # Test slow it down
        slow_prompt = "Keep the melody but slow it down."
        new_code4, exp4, is_comp4, _ = process_user_intent_and_compose(
            slow_prompt, previous_code=previous_code
        )
        self.assertTrue(is_comp4)
        self.assertIsNotNone(new_code4)
        self.assertIn("TEMPO 72;", new_code4)

        # Verify compile
        midi_path = os.path.join(self.temp_dir.name, "mod_flute.mid")
        ok, logs, errors, timeline, tracks, total_dur, bpm = execute_and_build_timeline(new_code2, midi_path)
        self.assertTrue(ok, f"Modified code failed to compile: {errors}")

    # -------------------------------------------------------------
    # Scenario G: Robustness & Edge Case Prompts
    # -------------------------------------------------------------
    def test_prompt_robustness_and_edge_cases(self):
        """Empty input, punctuation-only, whitespace, mixed-case, and embedded words."""
        # Empty and punctuation
        for empty_or_punct in ["", "   ", "???", "!!! ... ???", "   ---   "]:
            with self.subTest(prompt=empty_or_punct):
                code, exp, is_comp, _ = process_user_intent_and_compose(empty_or_punct)
                self.assertFalse(is_comp)
                self.assertIsNone(code)
                self.assertIn("describe the music", exp.lower())

        # Mixed capitalization and whitespace
        loud_prompt = "   CREATE A CHEERFUL PIANO MELODY AT 120 BPM   "
        code, exp, is_comp, _ = process_user_intent_and_compose(loud_prompt)
        self.assertTrue(is_comp)
        self.assertIsNotNone(code)
        self.assertIn("TEMPO 120;", code)
        self.assertIn("Piano", code)

        # Embedded instrument in trivia question
        trivia_with_inst = "What is the capital of France? I had lunch at the Piano Cafe."
        code2, exp2, is_comp2, _ = process_user_intent_and_compose(trivia_with_inst)
        self.assertFalse(is_comp2)
        self.assertIsNone(code2)
        self.assertIn("specialized", exp2.lower())

if __name__ == "__main__":
    unittest.main()
