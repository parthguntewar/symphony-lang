# SymphonyLang

**A domain-specific compiler that turns a custom programming language into real, playable music.**

SymphonyLang is a full compiler — lexer, parser, semantic analyzer, intermediate representation, optimizer, and **two independent code generation backends** — built from scratch in Python. Instead of compiling to machine code, SymphonyLang compiles to **music**: a `.mid` file (via a MIDI backend) or a custom stack-based bytecode (via a hand-built VM). The two backends are verified to always agree, and a graph-coloring channel allocator assigns MIDI channels the same way real compilers assign CPU registers.

> This project treats music purely as the *output domain*. Every classical compiler phase — lexical analysis, parsing with error recovery, scoped semantic analysis, three-address IR, multi-pass optimization, and dual-target code generation — is implemented in full.

---

## Why this project exists

Most student compiler projects stop at "lexer + parser for a toy calculator language." SymphonyLang instead implements a **complete language** with variables, expressions, control flow, functions with parameters and scope, and two full compilation targets — while staying easy to demo, since the output is something anyone can *hear*.

---

## Pipeline Overview

```
SymphonyLang source (.sym)
        │
        ▼
   ┌─────────┐
   │  Lexer  │  text -> tokens
   └────┬────┘
        ▼
   ┌─────────┐
   │ Parser  │  tokens -> AST  (recursive descent, panic-mode error recovery)
   └────┬────┘
        ▼
   ┌───────────────────┐
   │ Semantic Analyzer  │  scoped symbol table, type/note/duration validation
   └────────┬───────────┘
            ▼
      ┌───────────┐
      │ IR Gen    │  AST -> flat three-address-code instructions
      └─────┬─────┘
            ▼
      ┌───────────┐
      │ Optimizer │  constant folding -> constant propagation -> dead code elimination
      └─────┬─────┘
            │
   ┌────────┴────────┐
   ▼                  ▼
┌────────┐      ┌──────────────────┐
│  MIDI  │      │ Bytecode Compiler │
│Backend │      │        +          │
│(Target │      │   Stack-based VM  │
│   A)   │      │    (Target B)     │
└───┬────┘      └─────────┬────────┘
    ▼                     ▼
output.mid          VM execution trace
    │                     │
    └────────┬────────────┘
             ▼
   Automated cross-backend
   validation (both must agree)
```

A separate **Channel Allocator** module assigns MIDI channels to simultaneous `PARALLEL` tracks using graph coloring — the same algorithm family real compilers use for register allocation.

---

## Language Features

```
TEMPO 120;
INSTRUMENT Piano;

FUNCTION Riff(len)
    PLAY C4 quarter;
    PLAY D4 quarter;
ENDFUNCTION

LET x = 4;
IF x > 2 THEN
    CALL Riff(1);
ELSE
    PLAY D4 quarter;
ENDIF

FOR i = 1 TO 3
    PLAY G4 eighth;
ENDFOR

PARALLEL
    TRACK Piano
        PLAY C4 quarter;
    ENDTRACK
    TRACK Bass
        PLAY C2 quarter;
    ENDTRACK
ENDPARALLEL
```

- Variables, arithmetic (`+ - * /`), comparisons, unary negation
- `IF`/`ELSE`, `FOR`, `REPEAT` loops — each with its own scope
- `FUNCTION`/`CALL` with parameters and a real call stack
- Music primitives: `PLAY`, `REST`, `TEMPO`, `INSTRUMENT`, `TRACK`
- `PARALLEL` blocks to declare simultaneous tracks for channel allocation
- Full semantic validation: note/duration/instrument correctness, scope checking, function arity checking, redeclaration detection

### Supported Instruments

Instruments are declared using `INSTRUMENT <Name>;`. SymphonyLang maintains a single authoritative instrument registry (`instruments.py`) mapping melodic instruments to zero-based General MIDI program numbers:

| Instrument | General MIDI Program (0-based) | General MIDI Number (1-based) | Category |
|---|---:|---:|---|
| **Violin** | **40** | **41** | Strings |
| **Flute** | **73** | **74** | Woodwinds / Pipe |
| **Cello** | **42** | **43** | Strings |
| **Trumpet** | **56** | **57** | Brass |
| Piano | 0 | 1 | Keyboard (Default) |
| Guitar | 24 | 25 | Plucked String |
| Bass | 32 | 33 | Bass |
| Clarinet | 71 | 72 | Woodwinds |
| Saxophone | 65 | 66 | Woodwinds |
| Synth | 80 | 81 | Synth Lead |
| Organ | 19 | 20 | Organ |
| Drums | N/A | N/A | Percussion (dedicated channel 9) |

Capitalization is canonicalized consistently with TitleCase (e.g., `Violin`, `violin`, and `VIOLIN` resolve cleanly to `Violin`). Unsupported instrument names are rejected at compile time with informative diagnostics.

```
# Example Instrument Declarations
INSTRUMENT Violin;
INSTRUMENT Flute;
INSTRUMENT Cello;
INSTRUMENT Trumpet;
```

---

## Project Structure

```
SymphonyLang/
├── backend/
│   ├── tokens.py              # Token type definitions
│   ├── lexer.py                # Stage 1: text -> tokens
│   ├── ast_nodes.py            # AST node definitions
│   ├── parser.py                # Stage 2: tokens -> AST (recursive descent)
│   ├── symbol_table.py          # Nested-scope symbol table
│   ├── instruments.py           # Authoritative General MIDI instrument registry
│   ├── semantic_analyzer.py     # Stage 3: AST validation
│   ├── ir.py                     # Stage 4: AST -> three-address IR
│   ├── optimizer.py              # Stage 5: constant folding / propagation / DCE
│   ├── codegen_midi.py           # Stage 6a: IR -> MIDI (Target A)
│   ├── bytecode_compiler.py      # Stage 6b: IR -> stack bytecode (Target B)
│   ├── vm.py                      # Stage 6b: bytecode execution engine
│   ├── channel_allocator.py       # Graph-coloring MIDI channel assignment
│   ├── compare_backends.py        # Automated Target A vs Target B validation
│   ├── test_instruments.py       # Full automated test suite
│   └── test_invalid.py           # Invalid syntax/semantics rejection tests
├── grammar/
│   └── grammar.ebnf              # Formal language grammar
├── testcases/
│   ├── quintet_demo.sym          # 5-instrument demonstration arrangement
│   ├── *.sym                     # Sample programs
│   └── invalid/                  # Negative test cases
├── docs/                          # Architecture notes, report material
└── frontend/                      # (planned) editor + pipeline visualizer UI
```

---

## Running It

```bash
# Set up
python3 -m venv venv
source venv/bin/activate
pip install mido

cd backend

# Run the automated test suite
python3 -m unittest test_instruments.py

# Run invalid input rejection tests
python3 test_invalid.py

# Compile the Quintet demonstration program (Piano, Violin, Flute, Cello, Trumpet)
python3 compiler.py ../testcases/quintet_demo.sym quintet_output.mid

# Run cross-backend validation on the demonstration (Target A vs Target B)
python3 compare_backends.py ../testcases/quintet_demo.sym

# Run each stage individually (see each file's __main__ block for a demo)
python3 lexer.py
python3 parser.py
python3 semantic_analyzer.py
python3 ir.py
python3 optimizer.py
python3 codegen_midi.py          # produces output.mid
python3 bytecode_compiler.py
python3 vm.py
python3 channel_allocator.py
python3 compare_backends.py      # proves both backends agree
```

### Playing the Generated MIDI File

The generated `.mid` files (such as `quintet_output.mid` and `output.mid`) conform to the standard MIDI File Type 1 specification.
- **Desktop Players**: Open with Windows Media Player, VLC, QuickTime, or any standard media player.
- **DAWs / Synthesizers**: Import into GarageBand, Reaper, Ableton Live, Logic Pro, or MuseScore with a General MIDI soundfont.
- **CLI Players**: Use FluidSynth or Timidity++:
  ```bash
  fluidsynth -a dsound soundfont.sf2 quintet_output.mid
  ```

### MIDI Channel Allocation & Limitations

- The MIDI specification provides **16 channels** (0–15).
- Channel **9** (the 10th channel) is strictly reserved for percussion (`Drums`).
- The remaining **15 channels** (0–8, 10–15) are dynamically allocated to simultaneous melodic tracks using graph coloring.
- Up to **15 simultaneous melodic tracks** can play within any single `PARALLEL` block. Exceeding 15 simultaneous tracks raises an explicit `ChannelConflictError`.

---

## Design Highlights (for anyone reviewing the compiler theory)

- **Panic-mode error recovery**: the parser reports multiple syntax errors in a single pass instead of stopping at the first one.
- **Block-level lexical scoping**: every `IF`/`FOR`/`FUNCTION`/`REPEAT` body gets its own scope, correctly hiding declarations from the outer program — verified with dedicated scope-leak tests.
- **Three-address IR**: control flow (`IF`, `FOR`, `REPEAT`) is lowered into flat `LABEL`/`GOTO`/`IF_FALSE` instructions, the same representation real compilers use internally.
- **SSA-safe constant propagation**: propagation is restricted to compiler-generated temporaries (single-assignment by construction), deliberately excluding user variables that may be reassigned — a correctness-motivated design choice, not an oversight.
- **Target independence**: the exact same optimized IR feeds two unrelated execution engines (a MIDI event emitter and a stack-based VM). `compare_backends.py` automatically proves both produce identical musical output.
- **Register-allocation-style optimization**: the channel allocator builds an interference graph from `PARALLEL` track groupings and greedily colors it, directly mirroring how compilers assign physical CPU registers to live variables.

---

## Status

| Stage | Status |
|---|---|
| Lexer | ✅ |
| Parser (+ error recovery) | ✅ |
| Symbol Table (nested scopes) | ✅ |
| Semantic Analyzer | ✅ |
| IR Generator | ✅ |
| Optimizer (3 passes) | ✅ |
| MIDI Backend (Target A) | ✅ |
| Bytecode Compiler + VM (Target B) | ✅ |
| Cross-backend validation | ✅ |
| Channel Allocator (graph coloring) | ✅ |
| Formal test suite | ✅ |
| Frontend / pipeline visualizer UI | 🔲 planned |
| LLM-assisted natural-language front-end | 🔲 planned |

---

## Roadmap

- **Natural-language front-end**: a fine-tuned LLM translating plain-English music descriptions into SymphonyLang, with a compiler-feedback retry loop (compilation errors are fed back to the model for automatic correction).
- **Frontend UI**: an in-browser editor with a step-by-step visualizer for every compiler phase, plus in-browser MIDI playback.

---

