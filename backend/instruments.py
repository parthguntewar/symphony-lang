"""
instruments.py
Authoritative instrument registry for SymphonyLang.

Defines the supported instruments and their verified General MIDI program numbers
(0-indexed). Also handles canonicalization, case handling, and instrument validation.
"""

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
