from lexer import Lexer
from parser import Parser
from semantic_analyzer import SemanticAnalyzer
from ir import IRGenerator
from bytecode_compiler import BytecodeCompiler
from vm import VirtualMachine
from codegen_midi import MIDICodeGenerator

source = """
FUNCTION Riff(n, d)
    PLAY n d;
ENDFUNCTION

CALL Riff(C4, quarter);
"""

lexer = Lexer(source)
tokens, lex_errors = lexer.tokenize()

parser = Parser(tokens)
program, parse_errors = parser.parse()

analyzer = SemanticAnalyzer()
semantic_errors = analyzer.analyze(program)

ir = IRGenerator()
instructions = ir.generate(program)

print("Lexer errors:", lex_errors)
print("Parser errors:", parse_errors)
print("Semantic errors:", semantic_errors)

print("\nIR:")
for i, instr in enumerate(instructions):
    print(f"{i}: {instr}")

print("\n--- VM ---")
bytecode = BytecodeCompiler().compile(instructions)

for i, instr in enumerate(bytecode):
    print(f"{i}: {instr.opcode} {instr.operand}")

vm = VirtualMachine()
vm_events = vm.run(bytecode)

print("VM events:")
for event in vm_events:
    print(event.kind, event.data)

print("\n--- MIDI ---")
midi = MIDICodeGenerator()
track = midi.generate(instructions)

print("MIDI messages:")
for msg in track:
    if msg.type in ("note_on", "note_off"):
        print(msg)
