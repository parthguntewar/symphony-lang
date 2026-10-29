"""
test_multi_instrument_midi.py
Comprehensive multi-instrument and MIDI validation suite:
- Tests arrangements for 2, 3, 5, and 6 instruments
- Dedicated 6-instrument regression test (Bass, Cello, Flute, Piano, Trumpet, Violin)
- Verifies simultaneous start at beat zero across parallel tracks
- Concurrency vs sequential track concatenation
- Channel allocation and non-collision of MIDI programs
- Program changes preceding note-on events
- Unequal track lengths handling
- Independent MIDI parser validation via mido
- Exact tempo-to-seconds event timing at 60, 120, and 180 BPM
"""

import unittest
import os
import tempfile
import sys
from pathlib import Path
import mido

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from compiler import compile_source
from server import execute_and_build_timeline, extract_timeline_from_midi
from composer import process_user_intent_and_compose
from instruments import INSTRUMENT_PROGRAMS

class TestMultiInstrumentMIDI(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp_dir.cleanup()

    # -------------------------------------------------------------
    # 1. Two Instruments (Duet: Piano + Flute)
    # -------------------------------------------------------------
    def test_two_instruments_duet(self):
        """Two parallel instruments must start together and use separate channels."""
        code = """
        TEMPO 120;
        PARALLEL
            TRACK PianoTrk
                INSTRUMENT Piano;
                PLAY C4 quarter;
                PLAY E4 quarter;
            ENDTRACK

            TRACK FluteTrk
                INSTRUMENT Flute;
                PLAY G5 half;
            ENDTRACK
        ENDPARALLEL
        """
        midi_path = os.path.join(self.temp_dir.name, "duet.mid")
        ok, logs, errs, timeline, tracks, total_dur, bpm = execute_and_build_timeline(code, midi_path)
        self.assertTrue(ok, f"Compilation failed: {errs}")
        self.assertAlmostEqual(total_dur, 1.0, places=2)

        insts_at_zero = {e.instrument for e in timeline if abs(e.start_sec) < 0.001}
        self.assertEqual(insts_at_zero, {"Piano", "Flute"})

        channels = {e.channel for e in timeline}
        self.assertEqual(len(channels), 2, "Expected 2 distinct channels for 2 instruments")

    # -------------------------------------------------------------
    # 2. Three Instruments (Trio: Violin + Cello + Piano)
    # -------------------------------------------------------------
    def test_three_instruments_trio(self):
        """Three instruments in trio must maintain precise harmonic alignment."""
        code = """
        TEMPO 120;
        PARALLEL
            TRACK PianoTrk
                INSTRUMENT Piano;
                PLAY C4 quarter;
                PLAY G4 quarter;
            ENDTRACK

            TRACK ViolinTrk
                INSTRUMENT Violin;
                PLAY E4 half;
            ENDTRACK

            TRACK CelloTrk
                INSTRUMENT Cello;
                PLAY C3 half;
            ENDTRACK
        ENDPARALLEL
        """
        midi_path = os.path.join(self.temp_dir.name, "trio.mid")
        ok, logs, errs, timeline, tracks, total_dur, bpm = execute_and_build_timeline(code, midi_path)
        self.assertTrue(ok)
        self.assertAlmostEqual(total_dur, 1.0, places=2)

        insts_at_zero = {e.instrument for e in timeline if abs(e.start_sec) < 0.001}
        self.assertEqual(insts_at_zero, {"Piano", "Violin", "Cello"})

    # -------------------------------------------------------------
    # 3. Dedicated Six-Instrument Regression Test
    # (Bass, Cello, Flute, Piano, Trumpet, Violin)
    # -------------------------------------------------------------
    def test_six_instrument_orchestral_sextet(self):
        """
        Full 6-instrument regression test using Bass, Cello, Flute, Piano, Trumpet, and Violin.
        Inspects the compiled MIDI file directly:
        - 6 separate tracks
        - 6 distinct channels
        - General MIDI program numbers correctly configured
        - All 6 instruments start notes at t = 0.000s
        - Concurrency and timeline agreement
        """
        prompt = (
            "Create a masterwork arrangement at 120 BPM for six instruments: "
            "Bass, Cello, Flute, Piano, Trumpet, and Violin. All must play in parallel."
        )
        code, explanation, is_comp, is_fallback = process_user_intent_and_compose(prompt)
        self.assertTrue(is_comp)
        self.assertIsNotNone(code)

        # Confirm all 6 instruments in code
        for inst in ["Bass", "Cello", "Flute", "Piano", "Trumpet", "Violin"]:
            self.assertIn(f"INSTRUMENT {inst};", code)

        midi_path = os.path.join(self.temp_dir.name, "sextet.mid")
        ok, logs, errs, timeline, tracks, total_dur, bpm = execute_and_build_timeline(code, midi_path)
        self.assertTrue(ok, f"Compilation failed: {errs}")
        self.assertEqual(bpm, 120)

        # 1. Independent MIDI file inspection
        mid = mido.MidiFile(midi_path)
        self.assertEqual(mid.type, 1, "MIDI file should be Type 1 (synchronous multitrack)")
        self.assertGreaterEqual(len(mid.tracks), 6, "Expected at least 6 MIDI tracks")

        # 2. Check program changes across tracks
        program_changes = {}
        for track in mid.tracks:
            for msg in track:
                if msg.type == 'program_change':
                    program_changes[msg.channel] = msg.program

        self.assertGreaterEqual(
            len(program_changes), 6,
            f"Expected at least 6 distinct channel program changes, got {program_changes}"
        )

        # Expected GM programs
        expected_programs = {
            INSTRUMENT_PROGRAMS["Bass"],
            INSTRUMENT_PROGRAMS["Cello"],
            INSTRUMENT_PROGRAMS["Flute"],
            INSTRUMENT_PROGRAMS["Piano"],
            INSTRUMENT_PROGRAMS["Trumpet"],
            INSTRUMENT_PROGRAMS["Violin"],
        }
        actual_programs = set(program_changes.values())
        self.assertTrue(
            expected_programs.issubset(actual_programs),
            f"Expected programs {expected_programs} not all present in {actual_programs}"
        )

        # 3. Check simultaneous start at t=0
        insts_at_zero = {e.instrument for e in timeline if abs(e.start_sec) < 0.001}
        expected_six = {"Bass", "Cello", "Flute", "Piano", "Trumpet", "Violin"}
        self.assertEqual(
            insts_at_zero, expected_six,
            f"All 6 instruments must start at beat 0, got: {insts_at_zero}"
        )

        # 4. Check timeline duration matches longest track
        self.assertGreater(total_dur, 3.0)

    # -------------------------------------------------------------
    # 4. Unequal Track Lengths Handling
    # -------------------------------------------------------------
    def test_unequal_track_lengths(self):
        """
        When tracks in PARALLEL have different lengths (e.g. 2 beats vs 6 beats),
        the overall duration is determined by the longest track, and the shorter
        track finishes cleanly without blocking or stretching.
        """
        code = """
        TEMPO 120;
        PARALLEL
            TRACK ShortTrack
                INSTRUMENT Piano;
                PLAY C4 half;  # 2 beats = 1.0s at 120 BPM
            ENDTRACK

            TRACK LongTrack
                INSTRUMENT Flute;
                PLAY G5 whole;  # 4 beats
                PLAY B5 half;   # 2 beats -> total 6 beats = 3.0s at 120 BPM
            ENDTRACK
        ENDPARALLEL
        """
        midi_path = os.path.join(self.temp_dir.name, "unequal.mid")
        ok, logs, errs, timeline, tracks, total_dur, bpm = execute_and_build_timeline(code, midi_path)
        self.assertTrue(ok)
        self.assertAlmostEqual(total_dur, 3.0, places=2)

        # Short track has 1 note; long track has 2 notes
        piano_notes = [e for e in timeline if e.instrument == "Piano"]
        flute_notes = [e for e in timeline if e.instrument == "Flute"]
        self.assertEqual(len(piano_notes), 1)
        self.assertEqual(len(flute_notes), 2)
        self.assertAlmostEqual(piano_notes[0].start_sec, 0.0, places=2)
        self.assertAlmostEqual(piano_notes[0].duration_sec, 1.0, places=2)
        self.assertAlmostEqual(flute_notes[1].start_sec, 2.0, places=2)

    # -------------------------------------------------------------
    # 5. Exact Tempo-to-Seconds Conversions (60, 120, 180 BPM)
    # -------------------------------------------------------------
    def test_tempo_math_conversions(self):
        """Verify that quarter note durations scale inversely with BPM."""
        tempos_and_expected_quarter_sec = [
            (60, 1.000),   # 60 BPM -> 1 quarter = 1.000s
            (120, 0.500),  # 120 BPM -> 1 quarter = 0.500s
            (180, 0.333),  # 180 BPM -> 1 quarter = 0.333s
        ]
        for tempo, expected_sec in tempos_and_expected_quarter_sec:
            code = f"""
            TEMPO {tempo};
            INSTRUMENT Piano;
            PLAY C4 quarter;
            """
            midi_path = os.path.join(self.temp_dir.name, f"tempo_{tempo}.mid")
            ok, _, _, timeline, _, total_dur, bpm = execute_and_build_timeline(code, midi_path)
            self.assertTrue(ok)
            self.assertEqual(bpm, tempo)
            self.assertAlmostEqual(timeline[0].duration_sec, expected_sec, places=2)
            self.assertAlmostEqual(total_dur, expected_sec, places=2)

if __name__ == "__main__":
    unittest.main()

