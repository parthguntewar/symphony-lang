import sys
import os

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
from codegen_midi import MIDICodeGenerator
from bytecode_compiler import BytecodeCompiler
from vm import VirtualMachine


def compile_source(source_code):
    # 1. Lexing
    tokens, lex_errors = Lexer(source_code).tokenize()

    if lex_errors:
        print("Lexical errors:")
        for error in lex_errors:
            print(f"  {error}")
        return None

    # 2. Parsing
    ast, parse_errors = Parser(tokens).parse()

    if parse_errors:
        print("Parse errors:")
        for error in parse_errors:
            print(f"  {error}")
        return None

    # 3. Semantic analysis
    semantic_errors = SemanticAnalyzer().analyze(ast)

    if semantic_errors:
        print("Semantic errors:")
        for error in semantic_errors:
            print(f"  {error}")
        return None

    # 4. Generate IR
    ir = IRGenerator().generate(ast)

    # 5. Optimize IR
    ir, _ = constant_folding(ir)
    ir, _ = constant_propagation(ir)
    ir, _ = dead_code_elimination(ir)

    return ast, ir


def compile_file(source_path, output_path="output.mid"):
    print("=" * 60)
    print(f"Compiling: {source_path}")
    print("=" * 60)

    try:
        with open(source_path) as f:
            source_code = f.read()
    except OSError as e:
        print(f"Error reading source file: {e}")
        return False

    result = compile_source(source_code)

    if result is None:
        return False

    ast, ir = result

    print("\nCompilation stages: OK")
    print("  ✓ Lexing")
    print("  ✓ Parsing")
    print("  ✓ Semantic analysis")
    print("  ✓ IR generation")
    print("  ✓ Optimization")

    # 6. Allocate MIDI channels from AST
    channel_map, _ = allocate_channels(ast)

    print("\nChannel allocation:")
    if channel_map:
        for track, channel in channel_map.items():
            print(f"  {track} -> channel {channel}")
    else:
        print("  No explicit tracks")

    # 7. Generate MIDI
    codegen = MIDICodeGenerator(channel_map=channel_map)
    codegen.generate(ir)
    codegen.save(output_path)

    print(f"\n✓ MIDI generated: {output_path}")
    print(f"  MIDI tracks: {len(codegen.tracks)}")

    # 8. Compile and run bytecode VM
    bytecode = BytecodeCompiler().compile(ir)
    vm_events = VirtualMachine().run(bytecode)

    print(f"✓ VM executed: {len(vm_events)} events")

    print("\n" + "=" * 60)
    print("COMPILATION SUCCESS")
    print("=" * 60)

    return True


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python3 compiler.py <source.sym> [output.mid]")
        return 1

    source_path = sys.argv[1]

    if len(sys.argv) >= 3:
        output_path = sys.argv[2]
    else:
        output_path = "output.mid"

    success = compile_file(source_path, output_path)

    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())