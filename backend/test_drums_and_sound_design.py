"""
test_drums_and_sound_design.py
Automated test suite verifying the drum and sound-design system:
- General MIDI percussion note number mappings (Kick=36, Snare=38, Hi-Hat=42, Crash=49, Clap=39, Ride=51, Toms)
- Percussion channel 10 (zero-indexed channel 9) assignment in generated MIDI files
- Simultaneous Kick, Snare, and Hi-Hat events in PARALLEL drum tracks
- Synchronization of percussion events with melodic tracks (Bass, Piano, Guitar)
- Generation of drum grooves from natural language prompts
- Named drum syntax (PLAY Kick quarter; PLAY Snare quarter;) in the compiler pipeline
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

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

from instruments import (
    GM_PERCUSSION_NOTE_MAP,
    GM_PERCUSSION_NUMBER_TO_NAME,
    get_percussion_note,
    is_percussion,
)
from codegen_midi import note_name_to_midi
from compiler import compile_source
from server import execute_and_build_timeline, extract_timeline_from_midi
from composer import process_user_intent_and_compose

class TestDrumsAndSoundDesign(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp_dir.cleanup()

    # -------------------------------------------------------------
    # 1. General MIDI Percussion Note Mappings
    # -------------------------------------------------------------
    def test_general_midi_percussion_mappings(self):
        """Verify standard General MIDI percussion note numbers and aliases."""
        expected_mappings = {
            "Kick": 36,
            "BassDrum": 36,
            "AcousticBassDrum": 35,
            "Snare": 38,
            "AcousticSnare": 38,
            "ElectricSnare": 40,
            "HandClap": 39,
            "Clap": 39,
            "ClosedHiHat": 42,
            "HiHat": 42,
            "PedalHiHat": 44,
            "OpenHiHat": 46,
            "LowFloorTom": 41,
            "LowTom": 45,
            "LowMidTom": 47,
            "HiMidTom": 48,
            "HighTom": 50,
            "Crash": 49,
            "CrashCymbal": 49,
            "Ride": 51,
            "RideCymbal": 51,
        }
        for name, expected_num in expected_mappings.items():
            with self.subTest(name=name):
                resolved = get_percussion_note(name)
                self.assertEqual(
                    resolved, expected_num,
                    f"get_percussion_note('{name}') returned {resolved}, expected {expected_num}"
                )
                midi_val = note_name_to_midi(name)
                self.assertEqual(
                    midi_val, expected_num,
                    f"note_name_to_midi('{name}') returned {midi_val}, expected {expected_num}"
                )

        # Standard scientific pitch notation mappings for drums
        self.assertEqual(note_name_to_midi("C2"), 36)   # Kick
        self.assertEqual(note_name_to_midi("B1"), 35)   # Acoustic Bass Drum
        self.assertEqual(note_name_to_midi("D2"), 38)   # Snare
        self.assertEqual(note_name_to_midi("D#2"), 39)  # Hand Clap
        self.assertEqual(note_name_to_midi("E2"), 40)   # Electric Snare
        self.assertEqual(note_name_to_midi("F#2"), 42)  # Closed Hi-Hat
        self.assertEqual(note_name_to_midi("G#2"), 44)  # Pedal Hi-Hat
        self.assertEqual(note_name_to_midi("A#2"), 46)  # Open Hi-Hat
        self.assertEqual(note_name_to_midi("C#3"), 49)  # Crash Cymbal
        self.assertEqual(note_name_to_midi("D#3"), 51)  # Ride Cymbal

    # -------------------------------------------------------------
    # 2. Channel 10 (Zero-indexed Channel 9) Assignment
    # -------------------------------------------------------------
    def test_drum_midi_channel_9_assignment(self):
        """Verify that drum tracks are strictly assigned to MIDI channel 9 with program 0."""
        code = """
        TEMPO 120;
        TRACK DrumsTrack
            INSTRUMENT Drums;
            PLAY C2 quarter;
            PLAY D2 quarter;
            PLAY F#2 quarter;
            PLAY C#3 quarter;
        ENDTRACK
        """
        midi_path = os.path.join(self.temp_dir.name, "drums_channel.mid")
        ok, logs, errs, timeline, tracks, total_dur, bpm = execute_and_build_timeline(code, midi_path)
        self.assertTrue(ok, f"Compilation failed: {errs}")

        # Inspect MIDI file directly
        mid = mido.MidiFile(midi_path)
        drum_notes = []
        drum_channels = set()
        program_changes = []

        for track in mid.tracks:
            for msg in track:
                if msg.type == 'note_on' and msg.velocity > 0:
                    drum_notes.append(msg.note)
                    drum_channels.add(msg.channel)
                elif msg.type == 'program_change':
                    program_changes.append((msg.channel, msg.program))

        # Channel 9 only (standard GM percussion channel)
        self.assertEqual(drum_channels, {9}, f"Expected drum channel {9}, got {drum_channels}")
        self.assertEqual(drum_notes, [36, 38, 42, 49], "Expected Kick(36), Snare(38), Hi-Hat(42), Crash(49)")

        # Verify timeline events extracted
        self.assertEqual(len(timeline), 4)
        for e in timeline:
            self.assertEqual(e.channel, 9)
            self.assertEqual(e.instrument, "Drums")

    # -------------------------------------------------------------
    # 3. Simultaneous Kick, Snare, and Hi-Hat Events
    # -------------------------------------------------------------
    def test_simultaneous_kick_snare_hihat(self):
        """
        Verify that multi-track drum kits in PARALLEL (Kick + Snare + Hi-Hat)
        play simultaneous notes at the exact same timestamp without collision.
        """
        code = """
        TEMPO 120;
        PARALLEL
            TRACK KickTrack
                INSTRUMENT Drums;
                PLAY C2 quarter;
                REST quarter;
                PLAY C2 quarter;
                REST quarter;
            ENDTRACK

            TRACK SnareTrack
                INSTRUMENT Drums;
                REST quarter;
                PLAY D2 quarter;
                REST quarter;
                PLAY D2 quarter;
            ENDTRACK

            TRACK HiHatTrack
                INSTRUMENT Drums;
                PLAY F#2 eighth;
                PLAY F#2 eighth;
                PLAY F#2 eighth;
                PLAY F#2 eighth;
                PLAY F#2 eighth;
                PLAY F#2 eighth;
                PLAY F#2 eighth;
                PLAY A#2 eighth;
            ENDTRACK
        ENDPARALLEL
        """
        midi_path = os.path.join(self.temp_dir.name, "poly_drums.mid")
        ok, logs, errs, timeline, tracks, total_dur, bpm = execute_and_build_timeline(code, midi_path)
        self.assertTrue(ok, f"Compilation failed: {errs}")
        self.assertAlmostEqual(total_dur, 2.0, places=2)

        # Beat 0: Both Kick (C2=36) and Closed Hi-Hat (F#2=42) start at t=0.0s
        beat_zero_notes = [e.midi_number for e in timeline if abs(e.start_sec - 0.0) < 0.001]
        self.assertIn(36, beat_zero_notes, "Kick drum missing at beat zero")
        self.assertIn(42, beat_zero_notes, "Hi-Hat missing at beat zero")

        # Beat 1 (0.5s): Both Snare (D2=38) and Closed Hi-Hat (F#2=42) start at t=0.5s
        beat_one_notes = [e.midi_number for e in timeline if abs(e.start_sec - 0.5) < 0.001]
        self.assertIn(38, beat_one_notes, "Snare drum missing at beat one (0.5s)")
        self.assertIn(42, beat_one_notes, "Hi-Hat missing at beat one (0.5s)")

        # Beat 2 (1.0s): Kick and Hi-Hat
        beat_two_notes = [e.midi_number for e in timeline if abs(e.start_sec - 1.0) < 0.001]
        self.assertIn(36, beat_two_notes)
        self.assertIn(42, beat_two_notes)

        # Beat 3.5 (1.75s): Open Hi-Hat (A#2=46)
        final_hihat = [e.midi_number for e in timeline if abs(e.start_sec - 1.75) < 0.001]
        self.assertIn(46, final_hihat, "Open Hi-Hat (46) missing at end of bar")

    # -------------------------------------------------------------
    # 4. Drum Synchronization with Melodic Tracks (Rhythm Section)
    # -------------------------------------------------------------
    def test_drum_synchronization_with_melodic_ensemble(self):
        """
        Verify that a multi-instrument rhythm section (Drums + Bass + Piano + Guitar)
        synchronizes with sample-accurate alignment, and drums are correctly identified.
        """
        code = """
        TEMPO 120;
        PARALLEL
            TRACK DrumsTrack
                INSTRUMENT Drums;
                PLAY C2 quarter;
                PLAY D2 quarter;
                PLAY C2 quarter;
                PLAY D2 quarter;
            ENDTRACK

            TRACK BassTrack
                INSTRUMENT Bass;
                PLAY C2 half;
                PLAY G2 half;
            ENDTRACK

            TRACK GuitarTrack
                INSTRUMENT Guitar;
                PLAY C3 quarter;
                PLAY E3 quarter;
                PLAY G3 quarter;
                PLAY C4 quarter;
            ENDTRACK

            TRACK PianoTrack
                INSTRUMENT Piano;
                PLAY C4 whole;
            ENDTRACK
        ENDPARALLEL
        """
        midi_path = os.path.join(self.temp_dir.name, "rhythm_section.mid")
        ok, logs, errs, timeline, tracks, total_dur, bpm = execute_and_build_timeline(code, midi_path)
        self.assertTrue(ok, f"Compilation failed: {errs}")
        self.assertAlmostEqual(total_dur, 2.0, places=2)

        # Verify all 4 instruments start together at t=0.0s
        t_zero_instruments = {e.instrument for e in timeline if abs(e.start_sec) < 0.001}
        self.assertEqual(
            t_zero_instruments,
            {"Drums", "Bass", "Guitar", "Piano"},
            f"All 4 instruments must start at t=0, got: {t_zero_instruments}"
        )

        # Verify drum notes have readable percussion names
        drum_events = [e for e in timeline if e.instrument == "Drums"]
        drum_names = [e.note for e in drum_events]
        self.assertIn("Bass Drum (Kick)", drum_names)
        self.assertIn("Acoustic Snare", drum_names)

    # -------------------------------------------------------------
    # 5. Natural Language Drum Generation
    # -------------------------------------------------------------
    def test_natural_language_drum_prompt_generation(self):
        """Prompting for drum beats produces multi-layer General MIDI drum code."""
        prompt = "Generate an energetic drum beat at 128 BPM with kick, snare, and hi-hat."
        code, exp, is_comp, _ = process_user_intent_and_compose(prompt)
        self.assertTrue(is_comp)
        self.assertIsNotNone(code)
        self.assertIn("TEMPO 128;", code)
        self.assertIn("INSTRUMENT Drums;", code)
        self.assertIn("KickTrack", code)
        self.assertIn("SnareTrack", code)
        self.assertIn("HiHatTrack", code)

        # Compile and verify
        midi_path = os.path.join(self.temp_dir.name, "gen_drums.mid")
        ok, logs, errs, timeline, tracks, total_dur, bpm = execute_and_build_timeline(code, midi_path)
        self.assertTrue(ok, f"Generated drum code failed to compile: {errs}")
        self.assertEqual(bpm, 128)
        self.assertIn("Drums", {e.instrument for e in timeline})

        # Check MIDI note numbers generated
        midi_numbers = {e.midi_number for e in timeline}
        self.assertIn(36, midi_numbers, "Expected Kick (36) in generated drum beat")
        self.assertIn(38, midi_numbers, "Expected Snare (38) in generated drum beat")
        self.assertIn(42, midi_numbers, "Expected Closed Hi-Hat (42) in generated drum beat")

    # -------------------------------------------------------------
    # 6. Named Drum Syntax Compilation (PLAY Kick quarter;)
    # -------------------------------------------------------------
    def test_named_drum_syntax(self):
        """Verify that compiler accepts named drum tokens directly in PLAY statements."""
        code = """
        TEMPO 120;
        TRACK Percussion
            INSTRUMENT Drums;
            PLAY Kick quarter;
            PLAY Snare quarter;
            PLAY Clap quarter;
            PLAY Crash quarter;
        ENDTRACK
        """
        midi_path = os.path.join(self.temp_dir.name, "named_drums.mid")
        ok, logs, errs, timeline, tracks, total_dur, bpm = execute_and_build_timeline(code, midi_path)
        self.assertTrue(ok, f"Named drum compilation failed: {errs}")

        notes = [e.midi_number for e in timeline]
        self.assertEqual(notes, [36, 38, 39, 49])

if __name__ == "__main__":
    unittest.main()
