"""
test_timeline_sync.py
Automated test suite verifying multi-instrument synchronization,
event-time conversion, simultaneous track alignment, and playback durations.
"""

import unittest
import os
import tempfile
from pathlib import Path

# Add backend directory to path
import sys
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from server import execute_and_build_timeline, extract_timeline_from_midi
from compiler import compile_source

class TestTimelineSync(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_parallel_multi_instrument_simultaneous_start(self):
        """
        Verify that multiple instruments inside a PARALLEL block start
        at the exact same timestamp (0.000s) on a shared playback timeline.
        """
        code = """
        TEMPO 120;
        PARALLEL
            TRACK ViolinTrack
                INSTRUMENT Violin;
                PLAY C4 quarter;
                PLAY E4 quarter;
            ENDTRACK

            TRACK FluteTrack
                INSTRUMENT Flute;
                PLAY G5 quarter;
                PLAY B5 quarter;
            ENDTRACK

            TRACK CelloTrack
                INSTRUMENT Cello;
                PLAY C3 half;
            ENDTRACK
        ENDPARALLEL
        """
        mid_path = os.path.join(self.temp_dir.name, "multi.mid")
        ok, logs, errors, timeline, tracks, total_dur, bpm = execute_and_build_timeline(code, mid_path)

        self.assertTrue(ok, f"Compilation failed: {errors}")
        self.assertEqual(bpm, 120)
        self.assertAlmostEqual(total_dur, 1.0, places=2)  # 2 quarters / 1 half at 120 BPM = 1.0s

        # Find notes at t=0
        notes_at_zero = [e for e in timeline if abs(e.start_sec - 0.0) < 0.001]
        insts_at_zero = {e.instrument for e in notes_at_zero}

        # All 3 instruments MUST start simultaneously at t = 0.0s
        self.assertEqual(len(notes_at_zero), 3, "Expected 3 simultaneous notes at t=0")
        self.assertIn("Violin", insts_at_zero)
        self.assertIn("Flute", insts_at_zero)
        self.assertIn("Cello", insts_at_zero)

        # Check subsequent notes at t=0.5s
        notes_at_half = [e for e in timeline if abs(e.start_sec - 0.5) < 0.001]
        insts_at_half = {e.instrument for e in notes_at_half}
        self.assertEqual(len(notes_at_half), 2, "Expected 2 simultaneous notes at t=0.5s")
        self.assertIn("Violin", insts_at_half)
        self.assertIn("Flute", insts_at_half)

    def test_tempo_math_conversion(self):
        """
        Verify tempo to seconds conversion is mathematically exact:
        - At 60 BPM, 1 beat (quarter) = 1.000s
        - At 120 BPM, 1 beat (quarter) = 0.500s
        - At 180 BPM, 1 beat (quarter) = 0.333s
        """
        for test_bpm, expected_quarter_sec in [(60, 1.0), (120, 0.5), (240, 0.25)]:
            code = f"""
            TEMPO {test_bpm};
            INSTRUMENT Piano;
            PLAY C4 quarter;
            PLAY G4 half;
            """
            mid_path = os.path.join(self.temp_dir.name, f"tempo_{test_bpm}.mid")
            ok, logs, errors, timeline, tracks, total_dur, bpm = execute_and_build_timeline(code, mid_path)

            self.assertTrue(ok)
            self.assertEqual(bpm, test_bpm)
            self.assertEqual(len(timeline), 2)

            note1 = timeline[0]
            note2 = timeline[1]

            self.assertAlmostEqual(note1.start_sec, 0.0, places=3)
            self.assertAlmostEqual(note1.duration_sec, expected_quarter_sec, places=3)
            self.assertAlmostEqual(note2.start_sec, expected_quarter_sec, places=3)
            self.assertAlmostEqual(note2.duration_sec, expected_quarter_sec * 2.0, places=3)
            self.assertAlmostEqual(total_dur, expected_quarter_sec * 3.0, places=3)

    def test_quintet_demo_synchronization(self):
        """
        Verify that the Quintet demonstration (Piano, Violin, Flute, Cello, Trumpet)
        compiles and produces perfectly synchronized polyphonic notes.
        """
        quintet_sym = BASE_DIR.parent / "testcases" / "quintet_demo.sym"
        if not quintet_sym.is_file():
            self.skipTest("quintet_demo.sym not found")

        with open(quintet_sym) as f:
            code = f.read()

        mid_path = os.path.join(self.temp_dir.name, "quintet.mid")
        ok, logs, errors, timeline, tracks, total_dur, bpm = execute_and_build_timeline(code, mid_path)

        self.assertTrue(ok)
        self.assertEqual(bpm, 110)
        self.assertGreater(len(timeline), 30)

        # Verify that multiple instruments start at t=0.0s
        t0_notes = [e for e in timeline if abs(e.start_sec - 0.0) < 0.001]
        self.assertGreaterEqual(len(t0_notes), 3)

        # Verify timeline is monotonically sorted
        for i in range(len(timeline) - 1):
            self.assertLessEqual(timeline[i].start_sec, timeline[i+1].start_sec)

    def test_rests_and_offsets(self):
        """
        Verify that REST statements correctly offset note start times.
        """
        code = """
        TEMPO 120;
        INSTRUMENT Piano;
        REST quarter;
        PLAY C4 quarter;
        """
        mid_path = os.path.join(self.temp_dir.name, "rest.mid")
        ok, logs, errors, timeline, tracks, total_dur, bpm = execute_and_build_timeline(code, mid_path)

        self.assertTrue(ok)
        self.assertEqual(len(timeline), 1)
        # 1 quarter rest at 120 BPM = 0.5s offset
        self.assertAlmostEqual(timeline[0].start_sec, 0.5, places=2)
        self.assertAlmostEqual(total_dur, 1.0, places=2)

if __name__ == "__main__":
    unittest.main()
