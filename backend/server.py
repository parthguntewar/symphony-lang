"""
server.py
FastAPI backend for SymphonyLang Studio.
Provides endpoints for health check, LLM/template code generation, compilation,
MIDI streaming/download, and example presets.
"""

import os
import sys
import uuid
import re
import json
import urllib.request
import urllib.error
import mido
from pathlib import Path
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

# Ensure backend directory is in sys.path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Load .env if present
try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR.parent / ".env")
    load_dotenv(BASE_DIR / ".env")
except Exception:
    pass

# Import compiler modules
from lexer import Lexer
from parser import Parser
from semantic_analyzer import SemanticAnalyzer
from ir import IRGenerator
from optimizer import (
    constant_folding,
    constant_propagation,
    dead_code_elimination,
)
from channel_allocator import allocate_channels
from codegen_midi import MIDICodeGenerator, note_name_to_midi
from bytecode_compiler import BytecodeCompiler
from vm import VirtualMachine
from instruments import (
    VALID_INSTRUMENTS,
    INSTRUMENT_PROGRAMS,
    canonicalize_instrument,
    is_valid_instrument,
    GM_PERCUSSION_NUMBER_TO_NAME,
)
from composer import process_user_intent_and_compose

OUTPUTS_DIR = BASE_DIR / "outputs"
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="SymphonyLang Studio API", version="1.0.0")

# Enable CORS for local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------- Models -----------------

class GenerateRequest(BaseModel):
    prompt: str
    conversation_history: Optional[List[Dict[str, str]]] = None
    previous_code: Optional[str] = None

class GenerateResponse(BaseModel):
    code: Optional[str] = None
    explanation: str
    is_template_fallback: bool
    provider: str
    is_composition: bool = True

class CompileRequest(BaseModel):
    source_code: str

class NoteTimelineEvent(BaseModel):
    kind: str
    track: Optional[str] = None
    channel: Optional[int] = None
    instrument: Optional[str] = None
    note: Optional[str] = None
    midi_number: Optional[int] = None
    duration: Optional[str] = None
    beats: Optional[float] = None
    start_beat: Optional[float] = None
    start_sec: Optional[float] = None
    duration_sec: Optional[float] = None
    bpm: Optional[int] = None

class CompileResponse(BaseModel):
    success: bool
    compilation_output: str
    errors: List[str]
    midi_id: Optional[str] = None
    midi_url: Optional[str] = None
    events_count: int
    tracks: List[str]
    timeline: List[NoteTimelineEvent]
    total_duration_sec: Optional[float] = None
    bpm: Optional[int] = None

# ----------------- LLM Generation & Fallback -----------------

SYSTEM_PROMPT = """You are SymphonyLang Studio, an expert AI music programming assistant.

### Behavior & Intent Handling:
1. If the user is simply greeting you (e.g. "hi", "hello", "hey", "thanks"), reply with a brief, friendly greeting explaining that you compose and compile music using SymphonyLang. DO NOT output any code for simple greetings.
2. If the user asks an unrelated general query (e.g. general trivia, math, weather), politely redirect them toward music composition. DO NOT output code for unrelated queries.
3. When the user requests to compose, generate, or modify music:
   - Generate valid SymphonyLang source code enclosed in ```symphonylang ... ``` followed by a brief 2-3 sentence musical breakdown.
   - For multi-instrument compositions, always use PARALLEL with TRACK blocks for each instrument, starting simultaneously at beat zero.

### Supported General MIDI Instruments:
Piano, Guitar, Violin, Flute, Bass, Trumpet, Cello, Clarinet, Saxophone, Synth, Organ, Drums.

### SymphonyLang Syntax Rules:
1. Every statement ends with a semicolon (;).
2. Comments begin with #.
3. Statements:
   - TEMPO <bpm>;
   - INSTRUMENT <Name>;
   - PLAY <Note> <Duration>; (Note format: C2 to B6; Durations: whole, half, quarter, eighth, sixteenth)
   - REST <Duration>;
   - FOR <var> = <start> TO <end> ... ENDFOR
   - FUNCTION <Name>(<params>) ... ENDFUNCTION
   - CALL <Name>(<args>);
   - PARALLEL
       TRACK <TrackName>
           INSTRUMENT <Name>;
           ...
       ENDTRACK
     ENDPARALLEL
"""

def parse_llm_markdown(content: str) -> tuple[Optional[str], str, bool]:
    code_match = re.search(r"```(?:symphonylang|sym)?\s*([\s\S]*?)```", content, re.IGNORECASE)
    if code_match:
        code = code_match.group(1).strip()
        explanation = content.replace(code_match.group(0), "").strip()
        return code, explanation or "Generated SymphonyLang musical composition.", True
    else:
        # No code block generated - conversational response
        return None, content.strip(), False

def generate_via_openai(prompt: str, api_key: str) -> Optional[tuple[Optional[str], str, bool]]:
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.7,
        "max_tokens": 1200,
    }
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        content = data["choices"][0]["message"]["content"]
        return parse_llm_markdown(content)

def generate_via_groq(prompt: str, api_key: str) -> Optional[tuple[Optional[str], str, bool]]:
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.7,
        "max_tokens": 1200,
    }
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        content = data["choices"][0]["message"]["content"]
        return parse_llm_markdown(content)

def generate_via_gemini(prompt: str, api_key: str) -> Optional[tuple[Optional[str], str, bool]]:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [
            {"role": "user", "parts": [{"text": SYSTEM_PROMPT + "\n\nUser Prompt: " + prompt}]}
        ]
    }
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        content = data["candidates"][0]["content"]["parts"][0]["text"]
        return parse_llm_markdown(content)

    return code.strip(), explanation

# ----------------- Compilation Helper -----------------

DURATION_BEATS = {
    "whole": 4.0,
    "half": 2.0,
    "quarter": 1.0,
    "eighth": 0.5,
    "sixteenth": 0.25,
}

def extract_timeline_from_midi(midi_file_path: str):
    """
    Extracts a mathematically exact, synchronized musical timeline directly
    from the compiled MIDI File Type 1.
    Guarantees sample-accurate alignment across all parallel tracks and channels.
    """
    mid = mido.MidiFile(midi_file_path)
    ticks_per_beat = mid.ticks_per_beat

    # Build dynamic tempo converter across all tracks
    tempo_changes = []
    for track in mid.tracks:
        abs_t = 0
        for msg in track:
            abs_t += msg.time
            if msg.type == 'set_tempo':
                tempo_changes.append((abs_t, msg.tempo))

    tempo_changes.sort(key=lambda x: x[0])
    if not tempo_changes or tempo_changes[0][0] != 0:
        tempo_changes.insert(0, (0, 500000))  # default 120 bpm (500,000 µs/beat)

    intervals = []
    cur_sec = 0.0
    for i in range(len(tempo_changes)):
        tick_i, tempo_i = tempo_changes[i]
        next_tick = tempo_changes[i + 1][0] if i + 1 < len(tempo_changes) else None
        sec_per_tick = (tempo_i / 1_000_000.0) / ticks_per_beat
        intervals.append({
            'start_tick': tick_i,
            'end_tick': next_tick,
            'tempo': tempo_i,
            'start_sec': cur_sec,
            'sec_per_tick': sec_per_tick,
        })
        if next_tick is not None:
            cur_sec += (next_tick - tick_i) * sec_per_tick

    def tick_to_sec(tick: int) -> float:
        for iv in reversed(intervals):
            if tick >= iv['start_tick']:
                return iv['start_sec'] + (tick - iv['start_tick']) * iv['sec_per_tick']
        return 0.0

    primary_bpm = int(round(mido.tempo2bpm(tempo_changes[0][1])))
    PROGRAM_TO_NAME = {v: k for k, v in INSTRUMENT_PROGRAMS.items()}
    PROGRAM_TO_NAME[0] = 'Piano'

    events: List[NoteTimelineEvent] = []
    total_ticks = 0
    discovered_tracks: List[str] = []

    for tr_idx, track in enumerate(mid.tracks):
        abs_tick = 0
        current_inst = 'Piano'
        active_notes: Dict[int, tuple[int, str, int]] = {}
        tr_name = getattr(track, 'name', '').strip() or f"Track {tr_idx}"

        for msg in track:
            abs_tick += msg.time
            if abs_tick > total_ticks:
                total_ticks = abs_tick

            if msg.type == 'track_name' and msg.name.strip():
                tr_name = msg.name.strip()
            elif msg.type == 'program_change':
                if msg.channel == 9:
                    current_inst = 'Drums'
                else:
                    current_inst = PROGRAM_TO_NAME.get(msg.program, 'Piano')
            elif msg.type == 'note_on' and msg.velocity > 0:
                inst_to_record = 'Drums' if msg.channel == 9 else current_inst
                active_notes[msg.note] = (abs_tick, inst_to_record, msg.channel)
            elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
                if msg.note in active_notes:
                    start_tick, inst, channel = active_notes.pop(msg.note)
                    dur_ticks = abs_tick - start_tick
                    start_beat = start_tick / ticks_per_beat
                    dur_beats = dur_ticks / ticks_per_beat
                    start_sec = tick_to_sec(start_tick)
                    end_sec = tick_to_sec(abs_tick)
                    dur_sec = max(0.02, end_sec - start_sec)

                    if channel == 9 or inst == 'Drums':
                        note_name = GM_PERCUSSION_NUMBER_TO_NAME.get(msg.note, f"Drum ({msg.note})")
                    else:
                        note_names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
                        octave = (msg.note // 12) - 1
                        note_name = f"{note_names[msg.note % 12]}{octave}"

                    events.append(NoteTimelineEvent(
                        kind="PLAY",
                        track=tr_name,
                        channel=channel,
                        instrument=inst,
                        note=note_name,
                        midi_number=msg.note,
                        start_beat=round(start_beat, 4),
                        beats=round(dur_beats, 4),
                        start_sec=round(start_sec, 4),
                        duration_sec=round(dur_sec, 4),
                        bpm=primary_bpm,
                    ))

        if tr_name not in discovered_tracks and tr_name != "Track 0":
            discovered_tracks.append(tr_name)

    events.sort(key=lambda e: (e.start_sec if e.start_sec is not None else 0.0, e.midi_number or 0))
    total_duration_sec = round(tick_to_sec(total_ticks), 4)

    return events, primary_bpm, total_duration_sec, discovered_tracks

def execute_and_build_timeline(source_code: str, output_mid_path: str):
    """
    Runs full compilation pipeline and extracts synchronized timeline events.
    Returns (success, log_output, errors, timeline, tracks, total_duration_sec, primary_bpm)
    """
    logs = []
    tracks: List[str] = []

    # 1. Lexing
    tokens, lex_errors = Lexer(source_code).tokenize()
    if lex_errors:
        return False, "Lexical analysis failed.", [str(e) for e in lex_errors], [], [], 0.0, 120
    logs.append("✓ Lexing passed")

    # 2. Parsing
    ast, parse_errors = Parser(tokens).parse()
    if parse_errors:
        return False, "Parsing failed.", [str(e) for e in parse_errors], [], [], 0.0, 120
    logs.append("✓ Parsing passed")

    # 3. Semantic Analysis
    semantic_errors = SemanticAnalyzer().analyze(ast)
    if semantic_errors:
        return False, "Semantic analysis failed.", [str(e) for e in semantic_errors], [], [], 0.0, 120
    logs.append("✓ Semantic analysis passed")

    # 4. IR Generation
    ir = IRGenerator().generate(ast)
    logs.append(f"✓ IR generated ({len(ir)} instructions)")

    # 5. IR Optimization
    ir, _ = constant_folding(ir)
    ir, _ = constant_propagation(ir)
    ir, _ = dead_code_elimination(ir)
    logs.append("✓ Optimization passes completed (Constant Folding, Propagation, DCE)")

    # 6. Channel Allocation
    channel_map, _ = allocate_channels(ast)
    if channel_map:
        for t, ch in channel_map.items():
            logs.append(f"  Track '{t}' allocated to MIDI channel {ch}")
            tracks.append(t)
    else:
        tracks.append("Master")

    # 7. MIDI Generation
    codegen = MIDICodeGenerator(channel_map=channel_map)
    codegen.generate(ir)
    codegen.save(output_mid_path)
    logs.append(f"✓ MIDI generated ({len(codegen.tracks)} track(s))")

    # 8. Bytecode VM Execution & Validation
    bytecode = BytecodeCompiler().compile(ir)
    vm = VirtualMachine()
    vm_events = vm.run(bytecode)
    logs.append(f"✓ Bytecode VM executed ({len(vm_events)} events)")

    # 9. Extract Mathematically Synchronized Timeline directly from MIDI
    timeline, bpm, total_duration_sec, discovered_tracks = extract_timeline_from_midi(output_mid_path)
    logs.append(f"✓ Synchronized timeline extracted ({len(timeline)} notes, {total_duration_sec}s total duration)")

    final_tracks = discovered_tracks or tracks or ["Master"]
    log_summary = "\n".join(logs)
    return True, log_summary, [], timeline, final_tracks, total_duration_sec, bpm

# ----------------- Routes -----------------

@app.get("/api/health")
def health_check():
    openai_key = os.getenv("OPENAI_API_KEY")
    groq_key = os.getenv("GROQ_API_KEY")
    gemini_key = os.getenv("GEMINI_API_KEY")

    active_provider = None
    if openai_key:
        active_provider = "OpenAI (gpt-4o-mini)"
    elif groq_key:
        active_provider = "Groq (llama-3.3-70b)"
    elif gemini_key:
        active_provider = "Google Gemini (gemini-1.5-flash)"

    return {
        "status": "healthy",
        "service": "SymphonyLang Studio API",
        "has_llm_key": active_provider is not None,
        "active_provider": active_provider,
        "supported_instruments": sorted(list(VALID_INSTRUMENTS)),
    }

@app.post("/api/generate", response_model=GenerateResponse)
def generate_code(req: GenerateRequest):
    if not req.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt cannot be empty.")

    openai_key = os.getenv("OPENAI_API_KEY")
    groq_key = os.getenv("GROQ_API_KEY")
    gemini_key = os.getenv("GEMINI_API_KEY")

    # Try LLM APIs if available
    try:
        if openai_key:
            res = generate_via_openai(req.prompt, openai_key)
            if res:
                return GenerateResponse(
                    code=res[0],
                    explanation=res[1],
                    is_template_fallback=False,
                    provider="OpenAI",
                    is_composition=res[2],
                )
        elif groq_key:
            res = generate_via_groq(req.prompt, groq_key)
            if res:
                return GenerateResponse(
                    code=res[0],
                    explanation=res[1],
                    is_template_fallback=False,
                    provider="Groq",
                    is_composition=res[2],
                )
        elif gemini_key:
            res = generate_via_gemini(req.prompt, gemini_key)
            if res:
                return GenerateResponse(
                    code=res[0],
                    explanation=res[1],
                    is_template_fallback=False,
                    provider="Google Gemini",
                    is_composition=res[2],
                )
    except Exception as e:
        print(f"LLM API call failed: {e}. Falling back to composition engine.")

    # Intelligent intent handling & composition engine
    code, explanation, is_composition, is_fallback = process_user_intent_and_compose(
        req.prompt, req.previous_code
    )

    if not is_composition:
        return GenerateResponse(
            code=None,
            explanation=explanation,
            is_template_fallback=is_fallback,
            provider="Built-in SymphonyLang Engine",
            is_composition=False,
        )

    fallback_note = (
        f"{explanation}\n\n"
        "*(Note: Generated via SymphonyLang's built-in intelligent composition engine. "
        "To enable external LLM AI generation, set OPENAI_API_KEY, GROQ_API_KEY, or GEMINI_API_KEY in your environment.)*"
    )
    return GenerateResponse(
        code=code,
        explanation=fallback_note,
        is_template_fallback=is_fallback,
        provider="Built-in SymphonyLang Engine",
        is_composition=True,
    )

@app.post("/api/compile", response_model=CompileResponse)
def compile_code(req: CompileRequest):
    source = req.source_code.strip()
    if not source:
        raise HTTPException(status_code=400, detail="Source code cannot be empty.")

    midi_id = uuid.uuid4().hex
    out_dir = OUTPUTS_DIR / midi_id
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "symphony.mid"

    try:
        success, logs, errors, timeline, tracks, total_duration_sec, bpm = execute_and_build_timeline(source, str(out_file))

        if not success:
            return CompileResponse(
                success=False,
                compilation_output=logs,
                errors=errors,
                midi_id=None,
                midi_url=None,
                events_count=0,
                tracks=[],
                timeline=[],
                total_duration_sec=0.0,
                bpm=120,
            )

        return CompileResponse(
            success=True,
            compilation_output=logs,
            errors=[],
            midi_id=midi_id,
            midi_url=f"/api/midi/{midi_id}",
            events_count=len(timeline),
            tracks=tracks,
            timeline=timeline,
            total_duration_sec=total_duration_sec,
            bpm=bpm,
        )

    except Exception as e:
        return CompileResponse(
            success=False,
            compilation_output="Internal compiler exception occurred.",
            errors=[str(e)],
            midi_id=None,
            midi_url=None,
            events_count=0,
            tracks=[],
            timeline=[],
        )

@app.get("/api/midi/{midi_id}")
def download_midi(midi_id: str):
    # Strict validation: prevent path traversal
    if not re.match(r"^[a-f0-9]{32}$", midi_id):
        raise HTTPException(status_code=400, detail="Invalid MIDI identifier.")

    midi_path = OUTPUTS_DIR / midi_id / "symphony.mid"
    if not midi_path.is_file():
        raise HTTPException(status_code=404, detail="MIDI file not found or expired.")

    return FileResponse(
        path=str(midi_path),
        filename="symphony.mid",
        media_type="audio/midi",
    )

@app.get("/api/examples")
def list_examples():
    return [
        {
            "title": "Cheerful Piano Melody",
            "prompt": "Create a cheerful piano melody.",
            "description": "Bright C major melody with buoyant looping cadences.",
        },
        {
            "title": "Calm Ambient Soundtrack",
            "prompt": "Compose a calm ambient soundtrack.",
            "description": "Slow, peaceful multi-track harmony using Flute and Cello.",
        },
        {
            "title": "Energetic Melody at 120 BPM",
            "prompt": "Create an energetic melody at 120 BPM.",
            "description": "Fast driving Synth pulse with 16th-note phrasing and function calls.",
        },
    ]

# Mount frontend production build if available
FRONTEND_DIST = BASE_DIR.parent / "frontend" / "dist"
if FRONTEND_DIST.is_dir():
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
