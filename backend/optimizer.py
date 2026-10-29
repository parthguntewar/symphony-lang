"""
optimizer.py
Takes the flat IR instruction list (from ir.py) and simplifies it,
WITHOUT changing what the program actually does.

We build this as several small, separate passes - each one looking for
one specific kind of waste. This mirrors how real compilers are built
(e.g. GCC and LLVM both run many independent optimization passes).

Pass 1 implemented here: CONSTANT FOLDING
    If both operands of an arithmetic/comparison instruction are already
    known numbers at compile time (not variables), we can just compute
    the answer right now instead of making the final program do it later.

    Example:
        t1 = ADD(2, 2)      ->      t1 = ASSIGN(4)
        t2 = GT(10, 3)      ->      t2 = ASSIGN(True)   (well, 1/0 - see below)
"""

from ir import Instruction
import re


# Opcodes this pass knows how to fold, and the Python operation they map to.
ARITH_OPS = {
    'ADD': lambda a, b: a + b,
    'SUB': lambda a, b: a - b,
    'MUL': lambda a, b: a * b,
    'DIV': lambda a, b: a // b if b != 0 else None,  # integer division; guard divide-by-zero
}

COMPARE_OPS = {
    'LT': lambda a, b: 1 if a < b else 0,
    'GT': lambda a, b: 1 if a > b else 0,
    'LE': lambda a, b: 1 if a <= b else 0,
    'GE': lambda a, b: 1 if a >= b else 0,
    'EQ': lambda a, b: 1 if a == b else 0,
    'NE': lambda a, b: 1 if a != b else 0,
}

FOLDABLE_OPS = {**ARITH_OPS, **COMPARE_OPS}


def _is_number(x):
    return isinstance(x, int) and not isinstance(x, bool)


def constant_folding(instructions):
    """
    Scans every instruction. If it's an arithmetic/comparison op where
    BOTH operands are literal numbers (not variable/temp names), replace
    it with a plain ASSIGN of the computed value.

    Returns a NEW list (does not mutate the input), so we can compare
    before/after for the report.
    """
    new_instructions = []
    folded_count = 0

    for instr in instructions:
        if instr.opcode in FOLDABLE_OPS and len(instr.args) == 2:
            a, b = instr.args
            if _is_number(a) and _is_number(b):
                value = FOLDABLE_OPS[instr.opcode](a, b)
                if value is not None:  # None means e.g. divide-by-zero, don't fold
                    new_instructions.append(
                        Instruction('ASSIGN', [value], result=instr.result)
                    )
                    folded_count += 1
                    continue
        # Not foldable - keep as-is.
        new_instructions.append(instr)

    return new_instructions, folded_count


def _is_temp(name):
    """Temps (t1, t2, ...) are created fresh every time by the IR generator -
    each is assigned exactly once, so it's always safe to substitute them.
    User variables (x, y, i, ...) can be reassigned multiple times (e.g. in
    loops), so we deliberately do NOT propagate those - substituting them
    blindly could change what the program actually does."""
    return isinstance(name, str) and re.match(r'^t\d+$', name) is not None


def constant_propagation(instructions):
    """
    Tracks which temps are known to hold a constant literal value.
    Wherever that temp is used later, replaces it with the literal directly.

    Example:
        t1 = ASSIGN(120)
        TEMPO t1
    becomes:
        t1 = ASSIGN(120)      <- still here (removed by dead_code_elimination)
        TEMPO 120
    """
    const_map = {}  # temp name -> literal value
    new_instructions = []
    substitutions = 0

    for instr in instructions:
        new_args = []
        for a in instr.args:
            if isinstance(a, str) and a in const_map:
                new_args.append(const_map[a])
                substitutions += 1
            else:
                new_args.append(a)

        new_instr = Instruction(instr.opcode, new_args, instr.result)
        new_instructions.append(new_instr)

        # Record newly known constants (only for temps - see _is_temp docstring).
        if (instr.opcode == 'ASSIGN' and _is_temp(instr.result)
                and len(new_args) == 1 and _is_number(new_args[0])):
            const_map[instr.result] = new_args[0]

    return new_instructions, substitutions


# Opcodes that produce a value but have NO side effect - safe to delete
# if their result is never used anywhere else.
PURE_OPS = {'ASSIGN', 'ADD', 'SUB', 'MUL', 'DIV', 'NEG',
            'LT', 'GT', 'LE', 'GE', 'EQ', 'NE'}


def dead_code_elimination(instructions):
    """
    Removes instructions that compute a temp value which is never
    actually used anywhere later in the program. This is safe ONLY
    for "pure" instructions (no side effects) - we never delete things
    like PLAY, TEMPO, CALL, etc. even if their "result" looks unused,
    because they DO something beyond just producing a value.
    """
    used_names = set()
    for instr in instructions:
        for a in instr.args:
            if isinstance(a, str):
                used_names.add(a)

    new_instructions = []
    removed_count = 0
    for instr in instructions:
        if (instr.opcode in PURE_OPS and _is_temp(instr.result)
                and instr.result not in used_names):
            removed_count += 1
            continue
        new_instructions.append(instr)

    return new_instructions, removed_count



if __name__ == "__main__":
    from lexer import Lexer
    from parser import Parser
    from ir import IRGenerator, print_ir

    sample = """
    TEMPO 60+60;
    LET x = 2*4;
    LET y = 10 - 3;
    PLAY C4 quarter;
    """

    tokens, _ = Lexer(sample).tokenize()
    ast, parse_errors = Parser(tokens).parse()
    print("Parse errors:", parse_errors)

    ir = IRGenerator().generate(ast)
    print("\nBEFORE optimization:")
    print_ir(ir)

    step1, fold_count = constant_folding(ir)
    print(f"\nAFTER constant folding ({fold_count} folded):")
    print_ir(step1)

    step2, prop_count = constant_propagation(step1)
    print(f"\nAFTER constant propagation ({prop_count} substitution(s)):")
    print_ir(step2)

    step3, dce_count = dead_code_elimination(step2)
    print(f"\nAFTER dead code elimination ({dce_count} instruction(s) removed):")
    print_ir(step3)