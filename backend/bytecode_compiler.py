"""
bytecode_compiler.py
SECOND BACKEND (Target B): converts our existing IR (three-address code,
from ir.py) into a completely different instruction format - a STACK-BASED
BYTECODE, similar in spirit to Java bytecode or Python's .pyc format.

Why build this at all? To prove our compiler's IR is genuinely
TARGET-INDEPENDENT: the exact same IR that feeds codegen_midi.py (Target A)
can also feed this bytecode compiler (Target B), producing a totally
different kind of output consumed by a totally different kind of machine
(a stack-based VM instead of a MIDI file).

STACK MACHINE CONCEPT (for anyone unfamiliar):
Instead of "t1 = ADD(x, 2)" (three-address code, uses named variables),
a stack machine works like a calculator with a "push down" stack:
    PUSH x       -> stack: [x_value]
    PUSH 2       -> stack: [x_value, 2]
    ADD          -> pops both, pushes result -> stack: [x_value + 2]
Every operation just works on whatever is on TOP of the stack.
"""

from ir import Instruction


class BytecodeInstruction:
    """One bytecode instruction: an opcode plus optional operand(s).
    Deliberately simpler/flatter than IR's Instruction - real stack
    machines have very small, uniform instruction formats."""
    def __init__(self, opcode, operand=None):
        self.opcode = opcode
        self.operand = operand

    def __repr__(self):
        if self.operand is not None:
            return f"{self.opcode} {self.operand}"
        return f"{self.opcode}"


# Maps IR opcodes to bytecode opcodes for binary operations.
BINOP_MAP = {
    'ADD': 'ADD', 'SUB': 'SUB', 'MUL': 'MUL', 'DIV': 'DIV',
    'LT': 'LT', 'GT': 'GT', 'LE': 'LE', 'GE': 'GE', 'EQ': 'EQ', 'NE': 'NE',
}


class BytecodeCompiler:
    """
    Translates a list of IR Instructions (from ir.py) into a list of
    BytecodeInstructions for our stack-based VM.

    Key translation ideas:
      - Every IR temp/variable becomes a named memory SLOT the VM can
        LOAD from / STORE to (the VM keeps these in a simple dict).
      - Every arithmetic IR instruction becomes: PUSH left, PUSH right, OP.
      - LABEL/GOTO/IF_FALSE map directly to bytecode LABEL/JMP/JZ.
      - FUNC_BEGIN/FUNC_END/CALL/PARAM/RETURN map to a real call stack
        with its own local variable frame in the VM.
    """

    def __init__(self):
        self.bytecode = []

    def _emit(self, opcode, operand=None):
        self.bytecode.append(BytecodeInstruction(opcode, operand))

    def compile(self, ir_instructions):
        for instr in ir_instructions:
            self._compile_one(instr)
        self._emit('HALT')
        return self.bytecode

    def _push_value(self, value):
        """Push a literal number OR load a named variable/temp onto the stack."""
        if isinstance(value, (int, float)):
            self._emit('PUSH', value)
        else:
            self._emit('LOAD', value)

    def _compile_one(self, instr: Instruction):
        op = instr.opcode

        if op == 'ASSIGN':
            self._push_value(instr.args[0])
            self._emit('STORE', instr.result)

        elif op in BINOP_MAP:
            left, right = instr.args
            self._push_value(left)
            self._push_value(right)
            self._emit(BINOP_MAP[op])
            self._emit('STORE', instr.result)

        elif op == 'NEG':
            self._push_value(instr.args[0])
            self._emit('NEG')
            self._emit('STORE', instr.result)

        elif op == 'LABEL':
            self._emit('LABEL', instr.args[0])

        elif op == 'GOTO':
            self._emit('JMP', instr.args[0])

        elif op == 'IF_FALSE':
            self._push_value(instr.args[0])
            self._emit('JZ', instr.args[1])  # jump if top-of-stack is zero/false

        elif op == 'PLAY':
            note, duration = instr.args
            self._emit('PLAY', (note, duration))

        elif op == 'REST':
            self._emit('REST', instr.args[0])

        elif op == 'TEMPO':
            self._push_value(instr.args[0])
            self._emit('TEMPO')

        elif op == 'INSTRUMENT':
            self._emit('INSTR', instr.args[0])

        elif op == 'TRACK_BEGIN':
            self._emit('TRACK', instr.args[0])

        elif op == 'TRACK_END':
            self._emit('ENDTRACK', instr.args[0])

        elif op == 'FUNC_BEGIN':
            name = instr.args[0]
            params = instr.args[1:]
            self._emit('FUNC', (name, params))

        elif op == 'FUNC_END':
            self._emit('ENDFUNC', instr.args[0])

        elif op == 'PARAM':
            self._push_value(instr.args[0])
            self._emit('PARAM')

        elif op == 'CALL':
            name, nargs = instr.args
            self._emit('CALL', (name, nargs))
            if instr.result is not None:
                self._emit('STORE', instr.result)

        elif op == 'RETURN':
            if instr.args:
                self._push_value(instr.args[0])
                self._emit('RET_VAL')
            else:
                self._emit('RET')

        elif op == 'INCLUDE':
            pass

        else:
            raise ValueError(f"Bytecode compiler: unknown IR opcode {op}")


def print_bytecode(bytecode):
    for i, b in enumerate(bytecode):
        print(f"{i:3}: {b}")


if __name__ == "__main__":
    from lexer import Lexer
    from parser import Parser
    from ir import IRGenerator, print_ir
    from optimizer import constant_folding, constant_propagation, dead_code_elimination

    sample = open("../testcases/demo_sample.sym").read()

    tokens, _ = Lexer(sample).tokenize()
    ast, parse_errors = Parser(tokens).parse()
    print("Parse errors:", parse_errors)

    ir = IRGenerator().generate(ast)
    ir, _ = constant_folding(ir)
    ir, _ = constant_propagation(ir)
    ir, _ = dead_code_elimination(ir)

    print("\nOptimized IR (Target-independent, feeds BOTH backends):")
    print_ir(ir)

    bytecode = BytecodeCompiler().compile(ir)
    print("\nBytecode (Target B - Stack VM):")
    print_bytecode(bytecode)