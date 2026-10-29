"""
composer.py
Intelligent intent classification and musical composition engine for SymphonyLang.
Handles greetings, unrelated queries, modifications, single-instrument motifs,
and multi-instrument synchronized parallel arrangements.
"""

import re
from typing import Optional, Tuple, List, Dict, Any
from instruments import VALID_INSTRUMENTS, canonicalize_instrument, is_valid_instrument
from compiler import compile_source

# Common instruments outside SymphonyLang's General MIDI registry
UNSUPPORTED_INSTRUMENTS = {
    "harp", "tuba", "banjo", "accordion", "sitar", "oboe", "trombone",
    "french horn", "xylophone", "marimba", "viola", "bassoon", "ukulele",
    "mandolin", "bagpipes", "harmonica", "timpani", "recorder"
}

# Musical instrument register & motif definitions (all 16 beats = 4 bars)
INSTRUMENT_PARTS: Dict[str, List[str]] = {
    "Piano": [
        "PLAY C4 quarter;", "PLAY E4 quarter;", "PLAY G4 quarter;", "PLAY E4 quarter;",
        "PLAY A3 quarter;", "PLAY C4 quarter;", "PLAY E4 quarter;", "PLAY C4 quarter;",
        "PLAY F3 quarter;", "PLAY A3 quarter;", "PLAY C4 quarter;", "PLAY A3 quarter;",
        "PLAY G3 quarter;", "PLAY B3 quarter;", "PLAY D4 quarter;", "PLAY G4 quarter;",
    ],
    "Violin": [
        "PLAY E4 half;", "PLAY G4 half;",
        "PLAY C5 half;", "PLAY A4 half;",
        "PLAY A4 quarter;", "PLAY C5 quarter;", "PLAY D5 half;",
        "PLAY B4 half;", "PLAY C5 half;",
    ],
    "Flute": [
        "PLAY G5 quarter;", "PLAY C6 quarter;", "PLAY E6 half;",
        "PLAY D6 quarter;", "PLAY E6 quarter;", "PLAY F6 quarter;", "PLAY G6 quarter;",
        "PLAY A5 half;", "PLAY G5 half;",
        "PLAY F5 quarter;", "PLAY E5 quarter;", "PLAY D5 half;",
    ],
    "Cello": [
        "PLAY C3 half;", "PLAY G2 half;",
        "PLAY A2 half;", "PLAY F2 half;",
        "PLAY F2 half;", "PLAY D2 half;",
        "PLAY G2 half;", "PLAY C3 half;",
    ],
    "Trumpet": [
        "PLAY C4 half;", "PLAY G4 half;",
        "PLAY E4 half;", "PLAY A4 half;",
        "PLAY F4 quarter;", "PLAY A4 quarter;", "PLAY C5 half;",
        "PLAY G4 half;", "PLAY C5 half;",
    ],
    "Bass": [
        "PLAY C2 half;", "PLAY G2 half;",
        "PLAY A2 half;", "PLAY F2 half;",
        "PLAY F2 half;", "PLAY D2 half;",
        "PLAY G2 half;", "PLAY C2 half;",
    ],
    "Guitar": [
        "PLAY C3 quarter;", "PLAY G3 quarter;", "PLAY E4 quarter;", "PLAY G3 quarter;",
        "PLAY A3 quarter;", "PLAY E4 quarter;", "PLAY C4 quarter;", "PLAY E4 quarter;",
        "PLAY F3 quarter;", "PLAY C4 quarter;", "PLAY A4 quarter;", "PLAY C4 quarter;",
        "PLAY G3 quarter;", "PLAY D4 quarter;", "PLAY B4 quarter;", "PLAY G3 quarter;",
    ],
    "Drums": [
        "PLAY C2 quarter;", "PLAY D2 quarter;", "PLAY C2 quarter;", "PLAY D2 quarter;",
        "PLAY C2 quarter;", "PLAY D2 quarter;", "PLAY C2 eighth;", "PLAY C2 eighth;", "PLAY D2 quarter;",
        "PLAY C2 quarter;", "PLAY D#2 quarter;", "PLAY C2 quarter;", "PLAY D#2 quarter;",
        "PLAY C2 quarter;", "PLAY A2 eighth;", "PLAY D3 eighth;", "PLAY C#3 half;",
    ],
    "Saxophone": [
        "PLAY C4 half;", "PLAY E4 half;",
        "PLAY G4 quarter;", "PLAY A4 quarter;", "PLAY C5 half;",
        "PLAY D5 half;", "PLAY B4 half;",
        "PLAY A4 half;", "PLAY G4 half;",
    ],
    "Clarinet": [
        "PLAY E3 half;", "PLAY G3 half;",
        "PLAY C4 half;", "PLAY E4 half;",
        "PLAY F4 half;", "PLAY D4 half;",
        "PLAY B3 half;", "PLAY C4 half;",
    ],
    "Synth": [
        "PLAY C4 eighth;", "PLAY E4 eighth;", "PLAY G4 eighth;", "PLAY C5 eighth;",
        "PLAY B4 eighth;", "PLAY G4 eighth;", "PLAY E4 eighth;", "PLAY C4 eighth;",
        "PLAY A4 eighth;", "PLAY C5 eighth;", "PLAY E5 eighth;", "PLAY D5 eighth;",
        "PLAY B4 eighth;", "PLAY G4 eighth;", "PLAY A4 eighth;", "PLAY B4 eighth;",
        "PLAY C5 quarter;", "PLAY G4 quarter;", "PLAY E4 quarter;", "PLAY C4 quarter;",
        "PLAY D4 half;", "PLAY C4 half;",
    ],
    "Organ": [
        "PLAY C4 whole;",
        "PLAY A3 whole;",
        "PLAY F3 whole;",
        "PLAY G3 whole;",
    ],
}

def extract_tempo(prompt: str, default: int = 110) -> int:
    p = prompt.lower()
    m = re.search(r"(\d{2,3})\s*(?:bpm|tempo)", p)
    if m:
        return int(m.group(1))
    m2 = re.search(r"tempo\s*(?:of|at|to|=)?\s*(\d{2,3})", p)
    if m2:
        return int(m2.group(1))
    if any(w in p for w in ["calm", "ambient", "slow", "slower", "lullaby", "relax", "adagio"]):
        return 72
    if any(w in p for w in ["energetic", "fast", "faster", "driving", "intense", "speed", "allegro"]):
        return 130
    if any(w in p for w in ["cheerful", "happy", "bright", "joyful"]):
        return 116
    return default

def detect_instruments(prompt: str) -> Tuple[List[str], List[str]]:
    """
    Detects supported instruments and flags unsupported instruments mentioned in prompt.
    """
    p = prompt.lower()
    supported: List[str] = []
    unsupported: List[str] = []

    # Check unsupported instruments first
    for un in UNSUPPORTED_INSTRUMENTS:
        if re.search(rf"\b{un}\b", p):
            unsupported.append(un.title())

    # Check for specific supported instruments
    for inst in sorted(list(VALID_INSTRUMENTS)):
        if re.search(rf"\b{inst.lower()}\b", p):
            supported.append(inst)

    # Check common aliases
    if "sax" in p and "Saxophone" not in supported:
        supported.append("Saxophone")
    if "drum" in p and "Drums" not in supported:
        supported.append("Drums")
    if ("strings" in p or "string section" in p):
        if "Violin" not in supported:
            supported.append("Violin")
        if "Cello" not in supported:
            supported.append("Cello")
    if "brass" in p and "Trumpet" not in supported:
        supported.append("Trumpet")
    if "woodwinds" in p and "Flute" not in supported:
        supported.append("Flute")

    # Ensemble keywords
    if any(w in p for w in ["quintet", "five instruments", "5 instruments", "orchestral", "cinematic orchestral", "orchestra"]):
        needed = ["Piano", "Violin", "Flute", "Cello", "Trumpet"]
        for n in needed:
            if n not in supported:
                supported.append(n)
    elif "quartet" in p and len(supported) < 4:
        for n in ["Piano", "Violin", "Flute", "Cello"]:
            if n not in supported:
                supported.append(n)
    elif "trio" in p and len(supported) < 3:
        for n in ["Piano", "Violin", "Cello"]:
            if n not in supported:
                supported.append(n)

    return supported, unsupported

def is_greeting(prompt: str) -> bool:
    clean = prompt.strip().lower()
    clean = re.sub(r"[!.,?]+$", "", clean).strip()

    greeting_phrases = {
        "hi", "hello", "hey", "heya", "howdy", "sup", "yo", "greetings",
        "good morning", "good afternoon", "good evening", "good day",
        "thanks", "thank you", "thanks a lot", "thank you so much",
        "thanks for your help", "thx", "cheers", "hey there", "hello there", "hi there"
    }
    if clean in greeting_phrases:
        return True

    # Check short greetings with trailing text (e.g. "hey there!", "hello friend")
    greeting_starters = ["hi ", "hello ", "hey ", "thanks ", "thank you "]
    if len(clean) < 35 and any(clean.startswith(s) for s in greeting_starters):
        music_terms = {"music", "song", "melody", "beat", "compose", "track", "piano", "flute", "guitar"}
        if not any(term in clean for term in music_terms):
            return True

    return False

# Music-specific core vocabulary and instruments
CORE_MUSIC_KEYWORDS = {
    "music", "melody", "song", "soundtrack", "score", "rhythm", "tempo",
    "bpm", "orchestral", "cinematic", "ambient", "acoustic", "solo", "duet",
    "trio", "quartet", "quintet", "chord", "arpeggio", "symphony", "tune",
    "riff", "harmony", "notes", "instrument", "instruments", "synthesizer",
    "piano", "violin", "flute", "cello", "trumpet", "guitar", "bass",
    "drums", "saxophone", "clarinet", "synth", "organ", "reverb", "cadence",
    "polyphony", "octave", "scale", "ballad", "allegro", "andante", "adagio",
    "harp", "accordion", "sitar", "tuba", "compose", "composer", "composition"
}

def is_unrelated_query(prompt: str) -> bool:
    p = prompt.lower().strip()

    # If it's a greeting, that's handled separately
    if is_greeting(prompt):
        return False

    general_question_starters = [
        "what is", "what are", "who is", "who was", "where is", "when did",
        "why is", "how do", "how does", "tell me a joke", "write a python",
        "write a", "can you solve", "solve", "capital of", "weather",
        "translate", "recipe", "help me code", "write code", "explain"
    ]
    if any(start in p for start in general_question_starters):
        if not any(w in p for w in ["compose", "melody", "soundtrack", "parallel", "bpm", "symphonylang"]):
            return True

    words = set(re.findall(r"\b[a-z]+\b", p))
    has_music_intent = bool(words & CORE_MUSIC_KEYWORDS)

    if has_music_intent:
        return False

    # If no music keyword was found and input is not asking to modify or play anything
    return True

def handle_modification(prompt: str, previous_code: str) -> Tuple[Optional[str], str]:
    """
    Applies requested changes (tempo, instrument, adding tracks, etc.) to an existing composition.
    """
    p = prompt.lower()
    modified = previous_code
    changes = []

    # 1. Check tempo change
    new_tempo = extract_tempo(prompt, default=0)
    if new_tempo > 0:
        if re.search(r"TEMPO\s+\d+;", modified):
            modified = re.sub(r"TEMPO\s+\d+;", f"TEMPO {new_tempo};", modified)
            changes.append(f"adjusted tempo to {new_tempo} BPM")
        else:
            modified = f"TEMPO {new_tempo};\n" + modified
            changes.append(f"set tempo to {new_tempo} BPM")
    elif "faster" in p:
        cur_tempo_m = re.search(r"TEMPO\s+(\d+);", modified)
        if cur_tempo_m:
            cur_t = int(cur_tempo_m.group(1))
            new_t = min(240, cur_t + 20)
            modified = re.sub(r"TEMPO\s+\d+;", f"TEMPO {new_t};", modified)
            changes.append(f"increased tempo from {cur_t} to {new_t} BPM")
    elif "slower" in p or "slow" in p:
        cur_tempo_m = re.search(r"TEMPO\s+(\d+);", modified)
        if cur_tempo_m:
            cur_t = int(cur_tempo_m.group(1))
            new_t = max(40, cur_t - 20)
            modified = re.sub(r"TEMPO\s+\d+;", f"TEMPO {new_t};", modified)
            changes.append(f"decreased tempo from {cur_t} to {new_t} BPM")

    # 2. Check adding a track
    supported, _ = detect_instruments(prompt)
    if "add" in p and supported:
        add_inst = supported[0]
        part = INSTRUMENT_PARTS.get(add_inst, INSTRUMENT_PARTS["Piano"])
        track_lines = [f"    TRACK {add_inst}Track", f"        INSTRUMENT {add_inst};"]
        for stmt in part:
            track_lines.append(f"        {stmt}")
        track_lines.append("    ENDTRACK\n")
        new_track_str = "\n".join(track_lines)

        if "PARALLEL" in modified:
            modified = modified.replace("ENDPARALLEL", f"{new_track_str}\nENDPARALLEL")
            changes.append(f"added a new {add_inst} track in parallel")
        else:
            header_lines = []
            body_lines = []
            for line in modified.splitlines():
                if line.strip().startswith("TEMPO"):
                    header_lines.append(line)
                elif line.strip():
                    body_lines.append("        " + line.strip())

            wrapped = "\n".join(header_lines) + "\n\nPARALLEL\n    TRACK MainTrack\n" + "\n".join(body_lines) + "\n    ENDTRACK\n\n" + new_track_str + "ENDPARALLEL\n"
            modified = wrapped
            changes.append(f"converted to parallel arrangement and added {add_inst} track")

    # 3. Check instrument change / replacement
    elif supported and any(w in p for w in ["change", "replace", "switch", "instead", "to"]):
        new_inst = supported[0]
        if "PARALLEL" not in modified:
            if re.search(r"INSTRUMENT\s+\w+;", modified):
                modified = re.sub(r"INSTRUMENT\s+\w+;", f"INSTRUMENT {new_inst};", modified)
                changes.append(f"changed instrument to {new_inst}")
            else:
                modified = f"INSTRUMENT {new_inst};\n" + modified
                changes.append(f"set instrument to {new_inst}")
        else:
            m_target = re.search(r"(?:change|replace|switch)\s+(?:the\s+)?(\w+)\s+(?:to|with|instead)\s+(\w+)", p)
            if m_target:
                old_name = canonicalize_instrument(m_target.group(1))
                target_new = canonicalize_instrument(m_target.group(2)) or new_inst
                if old_name and target_new and old_name in modified:
                    modified = modified.replace(f"TRACK {old_name}Track", f"TRACK {target_new}Track")
                    modified = modified.replace(f"INSTRUMENT {old_name};", f"INSTRUMENT {target_new};")
                    changes.append(f"replaced {old_name} with {target_new}")
            else:
                modified = re.sub(r"INSTRUMENT\s+\w+;", f"INSTRUMENT {new_inst};", modified, count=1)
                changes.append(f"updated instrument to {new_inst}")

    # Verify syntax
    res = compile_source(modified)
    if res is not None:
        change_desc = "; ".join(changes) if changes else "applied requested modifications"
        return modified, f"Successfully {change_desc} while preserving the rest of your composition."
    return None, "Could not cleanly apply the modification to the existing code."

def generate_multi_instrument_composition(instruments: List[str], tempo: int, mood_desc: str = "") -> Tuple[str, str]:
    """
    Generates a synchronized parallel multi-track arrangement for the requested instruments.
    All tracks begin at beat 0, have distinct lines in appropriate registers, and overlap.
    """
    lines = [f"# Multi-Instrument Orchestral Arrangement ({', '.join(instruments)})", f"TEMPO {tempo};", "", "PARALLEL"]

    for inst in instruments:
        canonical = canonicalize_instrument(inst) or inst
        track_name = f"{canonical}Track"
        lines.append(f"    TRACK {track_name}")
        lines.append(f"        INSTRUMENT {canonical};")

        # Pick distinct motif for this instrument
        part = INSTRUMENT_PARTS.get(canonical, INSTRUMENT_PARTS["Piano"])
        for stmt in part:
            lines.append(f"        {stmt}")

        lines.append("    ENDTRACK")
        lines.append("")

    lines.append("ENDPARALLEL")
    code = "\n".join(lines)

    explanation = (
        f"Composed a synchronized {len(instruments)}-instrument arrangement at {tempo} BPM "
        f"featuring {', '.join(instruments)}. All instruments start simultaneously at beat zero "
        f"with dedicated harmonic, melodic, and bassline registers overlapping throughout."
    )
    return code, explanation

def generate_single_instrument_composition(inst: str, tempo: int, prompt: str) -> Tuple[str, str]:
    p = prompt.lower()
    canonical = canonicalize_instrument(inst) or "Piano"

    if canonical == "Drums":
        code = f"""# General MIDI Percussion Groove
TEMPO {tempo};

PARALLEL
    TRACK KickTrack
        INSTRUMENT Drums;
        # Bass Drum / Kick (C2 / MIDI 36)
        FOR bar = 1 TO 4
            PLAY C2 quarter;
            REST quarter;
            PLAY C2 quarter;
            REST quarter;
        ENDFOR
    ENDTRACK

    TRACK SnareTrack
        INSTRUMENT Drums;
        # Acoustic Snare (D2 / MIDI 38) and Clap (D#2 / MIDI 39)
        FOR bar = 1 TO 3
            REST quarter;
            PLAY D2 quarter;
            REST quarter;
            PLAY D2 quarter;
        ENDFOR
        # Tom fill into Crash Cymbal
        REST quarter;
        PLAY D2 quarter;
        PLAY A2 eighth;
        PLAY D3 eighth;
        PLAY C#3 quarter;
    ENDTRACK

    TRACK HiHatTrack
        INSTRUMENT Drums;
        # Closed Hi-Hat (F#2 / MIDI 42) & Open Hi-Hat (A#2 / MIDI 46)
        FOR beat = 1 TO 7
            PLAY F#2 eighth;
            PLAY F#2 eighth;
        ENDFOR
        PLAY A#2 quarter;
        FOR beat = 1 TO 7
            PLAY F#2 eighth;
            PLAY F#2 eighth;
        ENDFOR
        PLAY C#3 quarter;
    ENDTRACK
ENDPARALLEL
"""
        explanation = (
            f"Generated a synchronized multi-layered drum groove at {tempo} BPM on General MIDI percussion channel 10, "
            f"combining Kick (C2), Snare (D2), Closed/Open Hi-Hats (F#2/A#2), Toms, and Crash Cymbal (C#3)."
        )
        return code.strip(), explanation

    if "calm" in p or "ambient" in p or tempo <= 80:
        code = f"""# Calm Ambient Melody
TEMPO {tempo};
INSTRUMENT {canonical};

FUNCTION Theme()
    PLAY C4 half;
    PLAY E4 half;
    PLAY G4 whole;
    PLAY A4 half;
    PLAY F4 half;
    PLAY G4 whole;
ENDFUNCTION

CALL Theme();

FOR i = 1 TO 2
    PLAY E4 half;
    PLAY D4 half;
    PLAY C4 whole;
ENDFOR
"""
        explanation = f"Crafted a tranquil, peaceful melody for {canonical} at {tempo} BPM using sustained harmonic phrasing."

    elif "energetic" in p or "fast" in p or tempo >= 125:
        code = f"""# Energetic Driving Melody
TEMPO {tempo};
INSTRUMENT {canonical};

FUNCTION Riff(repeats)
    FOR step = 1 TO repeats
        PLAY C4 sixteenth;
        PLAY E4 sixteenth;
        PLAY G4 sixteenth;
        PLAY C5 eighth;
        PLAY B4 eighth;
        PLAY G4 eighth;
    ENDFOR
ENDFUNCTION

CALL Riff(2);

FOR loop = 1 TO 2
    PLAY A4 eighth;
    PLAY C5 eighth;
    PLAY E5 quarter;
    PLAY D5 eighth;
    PLAY B4 eighth;
    PLAY C5 quarter;
ENDFOR
"""
        explanation = f"Composed an energetic driving {canonical} motif at {tempo} BPM featuring fast rhythmic pulses and function calls."

    else:
        # Cheerful / balanced default
        code = f"""# Cheerful Melody
TEMPO {tempo};
INSTRUMENT {canonical};

PLAY C4 quarter;
PLAY E4 quarter;
PLAY G4 quarter;
PLAY C5 half;

PLAY B4 eighth;
PLAY A4 eighth;
PLAY G4 quarter;
PLAY E4 quarter;
PLAY G4 half;

FOR i = 1 TO 2
    PLAY F4 eighth;
    PLAY A4 eighth;
    PLAY C5 eighth;
    PLAY B4 eighth;
    PLAY G4 quarter;
ENDFOR

PLAY C4 whole;
"""
        explanation = f"Composed an uplifting {canonical} melody at {tempo} BPM with bright arpeggiated movement and cadence loops."

    return code.strip(), explanation

def process_user_intent_and_compose(
    prompt: str,
    previous_code: Optional[str] = None
) -> Tuple[Optional[str], str, bool, bool]:
    """
    Main entry point for intent handling and composition generation.
    Returns: (code, explanation, is_composition, is_fallback)
    """
    clean_prompt = prompt.strip()

    # Handle empty or punctuation-only prompts safely
    if not clean_prompt or not re.search(r"[a-zA-Z0-9]", clean_prompt):
        msg = (
            "Please describe the music you imagine! For example:\n\n"
            "• *'Create a cheerful piano melody at 120 BPM'*\n"
            "• *'Compose a calm ambient soundtrack with Flute and Cello'*\n"
            "• *'Create an energetic melody at 130 BPM using Synth and Drums'*"
        )
        return None, msg, False, True

    # 1. Greeting
    if is_greeting(clean_prompt):
        msg = (
            "Hello! I am your SymphonyLang musical assistant.\n\n"
            "You can describe any music you imagine—like instruments, tempo, mood, or a multi-track "
            "arrangement—and I will turn it into playable SymphonyLang code and standard MIDI music.\n\n"
            "Try asking for something like:\n"
            "• *'Create a cheerful piano melody at 120 BPM'*\n"
            "• *'Create a cinematic composition at 100 BPM using Piano, Violin, Flute, Cello, and Trumpet'*\n"
            "• *'Compose a calm ambient soundtrack'*."
        )
        return None, msg, False, True

    # 2. Unrelated questions
    if is_unrelated_query(clean_prompt):
        msg = (
            "I am a specialized AI music assistant designed to compose, compile, and play music using SymphonyLang.\n\n"
            "I cannot answer general knowledge or unrelated questions, but I'd love to help you make music! "
            "Please describe a melody, rhythm, or ensemble you'd like to hear."
        )
        return None, msg, False, True

    # 3. Modification of previous composition
    p_lower = clean_prompt.lower()
    if previous_code and any(w in p_lower for w in ["change", "modify", "faster", "slower", "replace", "switch", "tempo", "instead", "add", "slow"]):
        mod_code, mod_exp = handle_modification(clean_prompt, previous_code)
        if mod_code:
            return mod_code, mod_exp, True, True

    # 4. Instrument and Tempo Extraction
    supported, unsupported = detect_instruments(clean_prompt)
    tempo = extract_tempo(clean_prompt, default=110)

    # Check if only unsupported instruments were requested
    if unsupported and not supported:
        un_list = ", ".join(unsupported)
        valid_list = ", ".join(sorted(VALID_INSTRUMENTS))
        msg = (
            f"SymphonyLang's General MIDI registry does not currently support the requested unsupported instrument(s): {un_list}.\n\n"
            f"Supported instruments are: {valid_list}.\n\n"
            f"Would you like me to compose this using Piano, Guitar, Violin, or Synth instead?"
        )
        return None, msg, False, True

    # Multi-instrument vs Single instrument
    if len(supported) >= 2:
        code, explanation = generate_multi_instrument_composition(supported, tempo)
    elif len(supported) == 1:
        code, explanation = generate_single_instrument_composition(supported[0], tempo, clean_prompt)
    else:
        # Default single instrument (Piano)
        code, explanation = generate_single_instrument_composition("Piano", tempo, clean_prompt)

    # Mention unsupported instruments note if mixed
    if unsupported:
        explanation += f"\n\n*(Note: {', '.join(unsupported)} is not supported in SymphonyLang's General MIDI soundset and was omitted.)*"

    # Verify generated source code with the compiler
    res = compile_source(code)
    if res is None:
        # Attempt simple bounded recovery: check if semicolon missing
        fixed_code = "\n".join(line if line.strip().endswith(";") or line.strip().startswith("#") or line.strip() in ["PARALLEL", "ENDPARALLEL", "ENDTRACK"] or line.strip().startswith("TRACK") or line.strip().startswith("FOR") or line.strip() in ["ENDFOR", "ENDFUNCTION"] or line.strip().startswith("FUNCTION") else line + ";" for line in code.splitlines())
        if compile_source(fixed_code) is not None:
            code = fixed_code
        else:
            return None, "Error: Generated composition could not be validated by the SymphonyLang compiler.", False, True

    return code, explanation, True, True
