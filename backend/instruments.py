"""
instruments.py
Authoritative instrument registry for SymphonyLang.

Defines the supported instruments and their verified General MIDI program numbers
(0-indexed). Also handles canonicalization, case handling, and instrument validation.
"""

import re
from typing import Optional, Dict, Set

# General MIDI melodic instrument program numbers (0-indexed).
# GM 1-indexed numbers are 1 higher (e.g. Piano is GM 1, Violin is GM 41).
INSTRUMENT_PROGRAMS: Dict[str, int] = {
    "Piano": 0,       # Acoustic Grand Piano (GM 1)
    "Guitar": 24,     # Acoustic Guitar nylon (GM 25)
    "Violin": 40,     # Violin (GM 41)
    "Flute": 73,      # Flute (GM 74)
    "Bass": 32,       # Acoustic Bass (GM 33)
    "Trumpet": 56,    # Trumpet (GM 57)
    "Cello": 42,      # Cello / Violoncello (GM 43)
    "Clarinet": 71,   # Clarinet (GM 72)
    "Saxophone": 65,  # Alto Saxophone (GM 66)
    "Synth": 80,      # Lead 1 (square) (GM 81)
    "Organ": 19,      # Church Organ (GM 20)
}

# General MIDI percussion instruments (handled via dedicated MIDI channel 9)
PERCUSSION_INSTRUMENTS: Set[str] = {
    "Drums",
}

# General MIDI percussion note mapping (Standard Drum Kit on MIDI Channel 9 / Channel 10 1-based)
GM_PERCUSSION_NOTE_MAP: Dict[str, int] = {
    "acousticbassdrum": 35,
    "bassdrum": 36,
    "kick": 36,
    "sidestick": 37,
    "acousticsnare": 38,
    "snare": 38,
    "handclap": 39,
    "clap": 39,
    "electricsnare": 40,
    "lowfloortom": 41,
    "closedhihat": 42,
    "hihat": 42,
    "highfloortom": 43,
    "pedalhihat": 44,
    "lowtom": 45,
    "openhihat": 46,
    "lowmidtom": 47,
    "himidtom": 48,
    "crashcymbal1": 49,
    "crash": 49,
    "crashcymbal": 49,
    "hightom": 50,
    "ridecymbal1": 51,
    "ride": 51,
    "ridecymbal": 51,
    "chinesecymbal": 52,
    "ridebell": 53,
    "tambourine": 54,
    "splashcymbal": 55,
    "cowbell": 56,
    "crashcymbal2": 57,
    "vibraslap": 58,
    "ridecymbal2": 59,
}

# Reverse lookup: GM percussion note number -> readable name
GM_PERCUSSION_NUMBER_TO_NAME: Dict[int, str] = {
    35: "Acoustic Bass Drum",
    36: "Bass Drum (Kick)",
    37: "Side Stick",
    38: "Acoustic Snare",
    39: "Hand Clap",
    40: "Electric Snare",
    41: "Low Floor Tom",
    42: "Closed Hi-Hat",
    43: "High Floor Tom",
    44: "Pedal Hi-Hat",
    45: "Low Tom",
    46: "Open Hi-Hat",
    47: "Low-Mid Tom",
    48: "Hi-Mid Tom",
    49: "Crash Cymbal",
    50: "High Tom",
    51: "Ride Cymbal",
    52: "Chinese Cymbal",
    53: "Ride Bell",
    54: "Tambourine",
    55: "Splash Cymbal",
    56: "Cowbell",
    57: "Crash Cymbal 2",
    58: "Vibraslap",
    59: "Ride Cymbal 2",
}

def get_percussion_note(name: str) -> Optional[int]:
    """Resolves a percussion instrument name/alias to its General MIDI note number."""
    if not isinstance(name, str):
        return None
    cleaned = re.sub(r"[^a-zA-Z0-9]", "", name).lower()
    return GM_PERCUSSION_NOTE_MAP.get(cleaned)

# All valid canonical instrument names
VALID_INSTRUMENTS: Set[str] = set(INSTRUMENT_PROGRAMS.keys()) | PERCUSSION_INSTRUMENTS

# Lookup table for case-insensitive matching and convenient aliases
CANONICAL_ALIASES: Dict[str, str] = {
    name.lower(): name for name in VALID_INSTRUMENTS
}

# Useful common aliases consistent with existing conventions
CANONICAL_ALIASES.update({
    "sax": "Saxophone",
    "drum": "Drums",
    "percussion": "Drums",
})


def is_valid_instrument(name: str) -> bool:
    """Check if the given instrument name or alias is recognized."""
    if not isinstance(name, str):
        return False
    return name in VALID_INSTRUMENTS or name.lower() in CANONICAL_ALIASES


def canonicalize_instrument(name: str) -> Optional[str]:
    """
    Returns the canonical TitleCase instrument name for a given name or alias.
    Returns None if the instrument is unrecognized.
    """
    if not isinstance(name, str):
        return None
    if name in VALID_INSTRUMENTS:
        return name
    return CANONICAL_ALIASES.get(name.lower(), None)


def get_instrument_program(name: str) -> int:
    """
    Returns the zero-based General MIDI program number for the given instrument.
    Raises ValueError if the instrument is unknown or is a percussion instrument.
    """
    canonical = canonicalize_instrument(name)
    if canonical is None:
        raise ValueError(
            f"Unknown instrument '{name}'. "
            f"Valid options: {', '.join(sorted(VALID_INSTRUMENTS))}"
        )
    if canonical in PERCUSSION_INSTRUMENTS:
        raise ValueError(
            f"Instrument '{canonical}' is a percussion instrument and uses dedicated MIDI channel 9 "
            f"rather than a melodic program number."
        )
    return INSTRUMENT_PROGRAMS[canonical]


def is_percussion(name: str) -> bool:
    """Check if the given instrument is a percussion instrument."""
    canonical = canonicalize_instrument(name)
    return canonical in PERCUSSION_INSTRUMENTS
