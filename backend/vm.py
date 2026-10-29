"""
vm.py
A stack-based Virtual Machine that EXECUTES the bytecode produced by
bytecode_compiler.py. This is the second half of "Target B".

How a stack machine works, in plain terms:
    It keeps a list called the STACK. Instructions either:
      - push a value onto the stack (PUSH, LOAD)
      - pop value(s) off, compute something, push the result (ADD, GT, ...)
      - pop a value off and save it into memory (STORE)
    Nothing is ever referenced by name during computation - only by
    "whatever is currently on top of the stack". This is deliberately
    very different from how codegen_midi.py works (which reads IR
    directly and tracks named variables) - it's a genuinely separate
    execution engine, which is the whole point of building it.

We also maintain a proper CALL STACK for function calls: each call gets
its own local variable frame (its "activation record"), so parameters
and function-local temporaries don't clash with the caller's variables.
"""

import re

from instruments import canonicalize_instrument, is_valid_instrument

NOTE_PATTERN = re.compile(r"^[A-G](#|b)?\d$")
DURATIONS = {"whole", "half", "quarter", "eighth", "sixteenth"}

ARITH_OPS = {
    'ADD': lambda a, b: a + b, 'SUB': lambda a, b: a - b,
    'MUL': lambda a, b: a * b, 'DIV': lambda a, b: a // b if b != 0 else 0,
}
COMPARE_OPS = {
    'LT': lambda a, b: a < b, 'GT': lambda a, b: a > b,
    'LE': lambda a, b: a <= b, 'GE': lambda a, b: a >= b,
    'EQ': lambda a, b: a == b, 'NE': lambda a, b: a != b,
}


class VMEvent:
    """One observable output event produced while running the VM -
    used both for the demo trace and for comparing against the MIDI backend."""
    def __init__(self, kind, data):
        self.kind = kind   # 'PLAY' | 'REST' | 'TEMPO' | 'INSTRUMENT'
        self.data = data

    def __repr__(self):
        return f"VMEvent({self.kind}, {self.data})"


class VirtualMachine:
    def __init__(self):
        self.stack = []             # the operand stack
        self.events = []            # observable output (PLAY/REST/TEMPO/INSTRUMENT)
        self.max_steps = 200_000    # safety limit

    def run(self, bytecode):
        # Pre-scan: find label positions and function boundaries.
        label_map = {}
        func_map = {}
        for i, instr in enumerate(bytecode):
            if instr.opcode == 'LABEL':
                label_map[instr.operand] = i
            elif instr.opcode == 'FUNC':
                name, params = instr.operand
                func_map[name] = {'params': params, 'start': i + 1}

        globals_frame = {}
        frames = [globals_frame]     # call stack of local variable dicts
        return_addrs = []            # where to jump back to after RETURN
        param_queue = []             # values pushed by PARAM, consumed by CALL

        def current_frame():
            return frames[-1]

        def do_store(name):
            current_frame()[name] = self.stack.pop()

        def do_load(name):
            for frame in reversed(frames):
                if name in frame:
                    self.stack.append(frame[name])
                    return
            # Not a known variable - it's a raw literal string (rare, but safe fallback)
            self.stack.append(name)

        pc = 0
        steps = 0
        while pc < len(bytecode):
            steps += 1
            if steps > self.max_steps:
                raise RuntimeError("VM exceeded max step limit - possible infinite loop")

            instr = bytecode[pc]
            op = instr.opcode

            if op == 'HALT':
                break

            elif op == 'PUSH':
                self.stack.append(instr.operand)
                pc += 1

            elif op == 'LOAD':
                do_load(instr.operand)
                pc += 1

            elif op == 'STORE':
                do_store(instr.operand)
                pc += 1

            elif op in ARITH_OPS:
                b = self.stack.pop()
                a = self.stack.pop()
                self.stack.append(ARITH_OPS[op](a, b))
                pc += 1

            elif op in COMPARE_OPS:
                b = self.stack.pop()
                a = self.stack.pop()
                self.stack.append(COMPARE_OPS[op](a, b))
                pc += 1

            elif op == 'NEG':
                self.stack.append(-self.stack.pop())
                pc += 1

            elif op == 'LABEL':
                pc += 1

            elif op == 'JMP':
                pc = label_map[instr.operand]

            elif op == 'JZ':
                cond = self.stack.pop()
                pc = label_map[instr.operand] if not cond else pc + 1

            elif op == 'PLAY':
                note, duration = instr.operand
                if not NOTE_PATTERN.match(str(note)):
                    do_load(note)
                    note = self.stack.pop()
                if duration not in DURATIONS:
                    do_load(duration)
                    duration = self.stack.pop()
                self.events.append(VMEvent('PLAY', (note, duration)))
                pc += 1

            elif op == 'REST':
                self.events.append(VMEvent('REST', instr.operand))
                pc += 1

            elif op == 'TEMPO':
                bpm = self.stack.pop()
                self.events.append(VMEvent('TEMPO', bpm))
                pc += 1

            elif op == 'INSTR':
                canonical = canonicalize_instrument(instr.operand) or instr.operand
                self.events.append(VMEvent('INSTRUMENT', canonical))
                pc += 1

            elif op == 'TRACK':
                track_name = instr.operand
                self.events.append(VMEvent('TRACK', track_name))
                if is_valid_instrument(track_name):
                    canonical = canonicalize_instrument(track_name)
                    self.events.append(VMEvent('INSTRUMENT', canonical))
                pc += 1

            elif op == 'ENDTRACK':
                self.events.append(VMEvent('ENDTRACK', instr.operand))
                pc += 1

            elif op == 'FUNC':
                # Only reached via fall-through (shouldn't normally happen,
                # since a JMP always skips over function bodies at top level).
                pc += 1

            elif op == 'ENDFUNC':
                # Function fell through without RETURN - implicit return.
                if return_addrs:
                    frames.pop()
                    pc = return_addrs.pop()
                else:
                    pc += 1

            elif op == 'PARAM':
                param_queue.append(self.stack.pop())
                pc += 1

            elif op == 'CALL':
                name, nargs = instr.operand
                args = param_queue[len(param_queue) - nargs:] if nargs > 0 else []
                del param_queue[len(param_queue) - nargs:]
                finfo = func_map[name]
                new_frame = dict(zip(finfo['params'], args))
                frames.append(new_frame)
                return_addrs.append(pc + 1)
                pc = finfo['start']

            elif op == 'RET':
                frames.pop()
                pc = return_addrs.pop()

            elif op == 'RET_VAL':
                frames.pop()
                pc = return_addrs.pop()

            else:
                pc += 1  # unknown opcode - skip safely

        return self.events


def print_events(events):
    for e in events:
        print(" ", e)


if __name__ == "__main__":
    from lexer import Lexer
    from parser import Parser
    from ir import IRGenerator
    from optimizer import constant_folding, constant_propagation, dead_code_elimination
    from bytecode_compiler import BytecodeCompiler, print_bytecode

    sample = open("../testcases/demo_sample.sym").read()

    tokens, _ = Lexer(sample).tokenize()
    ast, parse_errors = Parser(tokens).parse()
    print("Parse errors:", parse_errors)

    ir = IRGenerator().generate(ast)
    ir, _ = constant_folding(ir)
    ir, _ = constant_propagation(ir)
    ir, _ = dead_code_elimination(ir)

    bytecode = BytecodeCompiler().compile(ir)
    print("\nBytecode:")
    print_bytecode(bytecode)

    vm = VirtualMachine()
    events = vm.run(bytecode)

    print("\nVM Execution Events (Target B output):")
    print_events(events)