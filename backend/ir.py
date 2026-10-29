"""
ir.py
Converts the AST into a flat, linear list of Instruction objects -
similar to "Three-Address Code" used in real compilers.

Why do this at all? Because a tree (AST) is great for checking correctness,
but hard to optimize or translate into a target format directly. A flat
instruction list is much easier to:
  - optimize (scan through and simplify/remove instructions)
  - translate into MIDI or bytecode (each instruction maps to a small,
    well-defined action)

Control flow (IF, FOR, REPEAT) is converted into LABELs and GOTOs here -
this is one of the most important ideas in compiler design: nested
structure becomes flat structure with jumps.
"""

from ast_nodes import (
    VarDecl, Assign, BinaryExpr, UnaryExpr, NumberLiteral, Identifier,
    NoteLiteral, DurationLiteral,
    IfStmt, ForStmt, RepeatStmt, FuncDecl, FuncCall, ReturnStmt,
    PlayStmt, RestStmt, TempoStmt, InstrumentStmt, TrackStmt, ParallelBlock, IncludeStmt,
)


class Instruction:
    """
    One IR instruction. Structured as: opcode + operands (+ optional result).
    Examples:
        Instruction('ASSIGN', result='x', args=[4])
        Instruction('ADD', result='t1', args=['x', 1])
        Instruction('LABEL', args=['L1'])
        Instruction('GOTO', args=['L1'])
        Instruction('IF_FALSE', args=['t1', 'L2'])
        Instruction('PLAY', args=['C4', 'quarter'])
    """
    def __init__(self, opcode, args=None, result=None):
        self.opcode = opcode
        self.args = args or []
        self.result = result

    def __repr__(self):
        if self.result is not None:
            args_str = ", ".join(str(a) for a in self.args)
            return f"{self.result} = {self.opcode}({args_str})"
        args_str = ", ".join(str(a) for a in self.args)
        return f"{self.opcode} {args_str}".rstrip()


class IRGenerator:
    def __init__(self):
        self.instructions = []
        self._temp_count = 0
        self._label_count = 0

    # ---------- helpers ----------

    def _new_temp(self):
        self._temp_count += 1
        return f"t{self._temp_count}"

    def _new_label(self):
        self._label_count += 1
        return f"L{self._label_count}"

    def _emit(self, opcode, args=None, result=None):
        instr = Instruction(opcode, args, result)
        self.instructions.append(instr)
        return instr

    # ---------- entry point ----------

    def generate(self, program):
        for stmt in program.statements:
            self._gen_stmt(stmt)
        return self.instructions

    # ---------- dispatch ----------

    def _gen_stmt(self, stmt):
        if isinstance(stmt, VarDecl):
            self._gen_var_decl(stmt)
        elif isinstance(stmt, Assign):
            self._gen_assign(stmt)
        elif isinstance(stmt, IfStmt):
            self._gen_if(stmt)
        elif isinstance(stmt, ForStmt):
            self._gen_for(stmt)
        elif isinstance(stmt, RepeatStmt):
            self._gen_repeat(stmt)
        elif isinstance(stmt, FuncDecl):
            self._gen_func_decl(stmt)
        elif isinstance(stmt, FuncCall):
            self._gen_func_call(stmt)
        elif isinstance(stmt, ReturnStmt):
            self._gen_return(stmt)
        elif isinstance(stmt, PlayStmt):
            self._emit('PLAY', [stmt.note, stmt.duration])
        elif isinstance(stmt, RestStmt):
            self._emit('REST', [stmt.duration])
        elif isinstance(stmt, TempoStmt):
            val = self._gen_expr(stmt.expr)
            self._emit('TEMPO', [val])
        elif isinstance(stmt, InstrumentStmt):
            self._emit('INSTRUMENT', [stmt.name])
        elif isinstance(stmt, TrackStmt):
            self._gen_track(stmt)
        elif isinstance(stmt, ParallelBlock):
            self._gen_parallel(stmt)
        elif isinstance(stmt, IncludeStmt):
            self._emit('INCLUDE', [stmt.filename])
        else:
            raise ValueError(f"IR generator: unknown statement {type(stmt).__name__}")

    # ---------- expressions ----------
    # Every expression returns something usable as an operand:
    # either a literal value, a variable name, or a temp variable name.

    def _gen_expr(self, expr):
        if isinstance(expr, NumberLiteral):
            return expr.value
        if isinstance(expr, NoteLiteral):
            return expr.value
        if isinstance(expr, DurationLiteral):
            return expr.value
        if isinstance(expr, Identifier):
            return expr.name
        if isinstance(expr, UnaryExpr):
            operand = self._gen_expr(expr.operand)
            temp = self._new_temp()
            self._emit('NEG', [operand], result=temp)
            return temp
        if isinstance(expr, BinaryExpr):
            left = self._gen_expr(expr.left)
            right = self._gen_expr(expr.right)
            temp = self._new_temp()
            opcode = self._binop_to_opcode(expr.op)
            self._emit(opcode, [left, right], result=temp)
            return temp
        if isinstance(expr, FuncCall):
            return self._gen_func_call(expr, as_expr=True)
        raise ValueError(f"IR generator: unknown expression {type(expr).__name__}")

    @staticmethod
    def _binop_to_opcode(op):
        return {
            '+': 'ADD', '-': 'SUB', '*': 'MUL', '/': 'DIV',
            '<': 'LT', '>': 'GT', '<=': 'LE', '>=': 'GE',
            '==': 'EQ', '!=': 'NE',
        }[op]

    # ---------- variables ----------

    def _gen_var_decl(self, node):
        val = self._gen_expr(node.expr)
        self._emit('ASSIGN', [val], result=node.name)

    def _gen_assign(self, node):
        val = self._gen_expr(node.expr)
        self._emit('ASSIGN', [val], result=node.name)

    # ---------- control flow ----------

    def _gen_if(self, node):
        cond = self._gen_expr(node.condition)
        label_else_or_end = self._new_label()
        self._emit('IF_FALSE', [cond, label_else_or_end])

        for s in node.then_body:
            self._gen_stmt(s)

        if node.else_body is not None:
            label_end = self._new_label()
            self._emit('GOTO', [label_end])
            self._emit('LABEL', [label_else_or_end])
            for s in node.else_body:
                self._gen_stmt(s)
            self._emit('LABEL', [label_end])
        else:
            self._emit('LABEL', [label_else_or_end])

    def _gen_for(self, node):
        start_val = self._gen_expr(node.start_expr)
        self._emit('ASSIGN', [start_val], result=node.var_name)

        label_start = self._new_label()
        label_end = self._new_label()
        self._emit('LABEL', [label_start])

        end_val = self._gen_expr(node.end_expr)
        cond_temp = self._new_temp()
        self._emit('LE', [node.var_name, end_val], result=cond_temp)
        self._emit('IF_FALSE', [cond_temp, label_end])

        for s in node.body:
            self._gen_stmt(s)

        step_temp = self._new_temp()
        self._emit('ADD', [node.var_name, 1], result=step_temp)
        self._emit('ASSIGN', [step_temp], result=node.var_name)
        self._emit('GOTO', [label_start])
        self._emit('LABEL', [label_end])

    def _gen_repeat(self, node):
        count_val = self._gen_expr(node.count_expr)
        counter = self._new_temp()
        self._emit('ASSIGN', [count_val], result=counter)

        label_start = self._new_label()
        label_end = self._new_label()
        self._emit('LABEL', [label_start])

        cond_temp = self._new_temp()
        self._emit('GT', [counter, 0], result=cond_temp)
        self._emit('IF_FALSE', [cond_temp, label_end])

        for s in node.body:
            self._gen_stmt(s)

        dec_temp = self._new_temp()
        self._emit('SUB', [counter, 1], result=dec_temp)
        self._emit('ASSIGN', [dec_temp], result=counter)
        self._emit('GOTO', [label_start])
        self._emit('LABEL', [label_end])

    # ---------- functions ----------

    def _gen_func_decl(self, node):
        skip_label = self._new_label()
        # Jump over the function body during normal top-to-bottom execution -
        # the body only runs when explicitly CALLed.
        self._emit('GOTO', [skip_label])

        self._emit('FUNC_BEGIN', [node.name] + node.params)
        for s in node.body:
            self._gen_stmt(s)
        self._emit('FUNC_END', [node.name])

        self._emit('LABEL', [skip_label])

    def _gen_func_call(self, node, as_expr=False):
        arg_vals = [self._gen_expr(a) for a in node.args]
        for v in arg_vals:
            self._emit('PARAM', [v])
        if as_expr:
            temp = self._new_temp()
            self._emit('CALL', [node.name, len(arg_vals)], result=temp)
            return temp
        else:
            self._emit('CALL', [node.name, len(arg_vals)])
            return None

    def _gen_return(self, node):
        if node.expr is not None:
            val = self._gen_expr(node.expr)
            self._emit('RETURN', [val])
        else:
            self._emit('RETURN', [])

    # ---------- music-specific ----------

    def _gen_track(self, node):
        self._emit('TRACK_BEGIN', [node.name])
        for s in node.body:
            self._gen_stmt(s)
        self._emit('TRACK_END', [node.name])

    def _gen_parallel(self, node):
        for track in node.tracks:
            self._gen_track(track)


def print_ir(instructions):
    """Pretty-print IR with line numbers, indenting nothing (flat by design)."""
    for i, instr in enumerate(instructions):
        print(f"{i:3}: {instr}")


if __name__ == "__main__":
    from lexer import Lexer
    from parser import Parser

    sample = """
    TEMPO 120;
    INSTRUMENT Piano;

    LET x = 4;
    IF x > 2 THEN
        PLAY C4 quarter;
    ELSE
        PLAY D4 quarter;
    ENDIF

    FOR i = 1 TO 3
        PLAY G4 whole;
    ENDFOR

    REPEAT 2
        REST half;
    ENDREPEAT
    """

    tokens, lex_errors = Lexer(sample).tokenize()
    ast, parse_errors = Parser(tokens).parse()
    print("Parse errors:", parse_errors)
    print()

    irgen = IRGenerator()
    ir = irgen.generate(ast)
    print_ir(ir)