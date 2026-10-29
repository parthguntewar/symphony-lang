"""
semantic_analyzer.py
Walks the AST produced by the Parser and checks that the program actually
makes SENSE, not just that it's grammatically correct. This is where we
catch things like:
    - using a variable that was never declared
    - calling a function that doesn't exist, or with the wrong number of args
    - invalid musical notes (e.g. Z9)
    - invalid durations
    - negative/zero tempo or repeat counts
    - re-declaring the same name twice in the same scope

Every block (FUNCTION body, IF branches, FOR body, REPEAT body, TRACK body)
gets its OWN scope, so a variable declared inside one doesn't leak outside it -
just like in a real programming language.
"""

from ast_nodes import (
    VarDecl, Assign, BinaryExpr, UnaryExpr, NumberLiteral, Identifier,
    NoteLiteral, DurationLiteral,
    IfStmt, ForStmt, RepeatStmt, FuncDecl, FuncCall, ReturnStmt,
    PlayStmt, RestStmt, TempoStmt, InstrumentStmt, TrackStmt, ParallelBlock, IncludeStmt,
)
from symbol_table import SymbolTable, SymbolAlreadyDeclared
from tokens import DURATIONS
import re

NOTE_PATTERN = re.compile(r"^[A-G](#|b)?\d$")

from instruments import (
    VALID_INSTRUMENTS,
    is_valid_instrument,
    canonicalize_instrument,
    get_percussion_note,
)


class SemanticError:
    def __init__(self, message, line):
        self.message = message
        self.line = line

    def __repr__(self):
        return f"SemanticError(line={self.line}): {self.message}"


class SemanticAnalyzer:
    def __init__(self):
        self.symtab = SymbolTable()
        self.errors = []
        # Tracks whether we're currently inside a function body,
        # so we can check RETURN is only used there.
        self.function_depth = 0

    def analyze(self, program):
        for stmt in program.statements:
            self._visit_stmt(stmt)
        return self.errors

    def _error(self, message, line):
        self.errors.append(SemanticError(message, line))

    # ---------- dispatch ----------

    def _visit_stmt(self, stmt):
        if isinstance(stmt, VarDecl):
            self._visit_var_decl(stmt)
        elif isinstance(stmt, Assign):
            self._visit_assign(stmt)
        elif isinstance(stmt, IfStmt):
            self._visit_if(stmt)
        elif isinstance(stmt, ForStmt):
            self._visit_for(stmt)
        elif isinstance(stmt, RepeatStmt):
            self._visit_repeat(stmt)
        elif isinstance(stmt, FuncDecl):
            self._visit_func_decl(stmt)
        elif isinstance(stmt, FuncCall):
            self._visit_func_call(stmt)
        elif isinstance(stmt, ReturnStmt):
            self._visit_return(stmt)
        elif isinstance(stmt, PlayStmt):
            self._visit_play(stmt)
        elif isinstance(stmt, RestStmt):
            self._visit_rest(stmt)
        elif isinstance(stmt, TempoStmt):
            self._visit_tempo(stmt)
        elif isinstance(stmt, InstrumentStmt):
            self._visit_instrument(stmt)
        elif isinstance(stmt, TrackStmt):
            self._visit_track(stmt)
        elif isinstance(stmt, ParallelBlock):
            self._visit_parallel(stmt)
        elif isinstance(stmt, IncludeStmt):
            pass  # file resolution handled separately (linking stage)
        else:
            self._error(f"Unknown statement node: {type(stmt).__name__}", 0)

    def _visit_block(self, statements):
        """Enter a new scope, visit all statements, then exit the scope."""
        self.symtab.enter_scope()
        for stmt in statements:
            self._visit_stmt(stmt)
        self.symtab.exit_scope()

    # ---------- variables & expressions ----------

    def _visit_var_decl(self, node):
        self._visit_expr(node.expr)
        try:
            self.symtab.declare(node.name, "variable", node.line)
        except SymbolAlreadyDeclared as e:
            self._error(str(e), node.line)

    def _visit_assign(self, node):
        self._visit_expr(node.expr)
        if not self.symtab.is_declared(node.name):
            self._error(
                f"Cannot assign to '{node.name}': it was never declared (use LET first)",
                node.line,
            )

    def _const_value(self, expr):
        """If expr is a compile-time-known number (e.g. 5, or -5 via UnaryExpr),
        return its integer value. Otherwise return None (e.g. it's a variable)."""
        if isinstance(expr, NumberLiteral):
            return expr.value
        if isinstance(expr, UnaryExpr) and expr.op == "-":
            inner = self._const_value(expr.operand)
            if inner is not None:
                return -inner
        return None

    def _visit_expr(self, expr):
        if isinstance(expr, NumberLiteral):
            return
        if isinstance(expr, NoteLiteral):
            return
        if isinstance(expr, DurationLiteral):
            return
        if isinstance(expr, Identifier):
            if not self.symtab.is_declared(expr.name):
                self._error(f"Use of undeclared variable '{expr.name}'", expr.line)
            return
        if isinstance(expr, BinaryExpr):
            self._visit_expr(expr.left)
            self._visit_expr(expr.right)
            return
        if isinstance(expr, UnaryExpr):
            self._visit_expr(expr.operand)
            return
        if isinstance(expr, FuncCall):
            self._visit_func_call(expr)
            return
        self._error(f"Unknown expression node: {type(expr).__name__}", 0)

    # ---------- control flow ----------

    def _visit_if(self, node):
        self._visit_expr(node.condition)
        self._visit_block(node.then_body)
        if node.else_body is not None:
            self._visit_block(node.else_body)

    def _visit_for(self, node):
        self._visit_expr(node.start_expr)
        self._visit_expr(node.end_expr)
        # Loop variable belongs to the loop's own scope.
        self.symtab.enter_scope()
        try:
            self.symtab.declare(node.var_name, "variable", node.line)
        except SymbolAlreadyDeclared as e:
            self._error(str(e), node.line)
        for stmt in node.body:
            self._visit_stmt(stmt)
        self.symtab.exit_scope()

    def _visit_repeat(self, node):
        self._visit_expr(node.count_expr)
        value = self._const_value(node.count_expr)
        if value is not None and value <= 0:
            self._error(f"REPEAT count must be positive, got {value}", node.line)
        self._visit_block(node.body)

    # ---------- functions ----------

    def _visit_func_decl(self, node):
        try:
            self.symtab.declare(
                node.name, "function", node.line, extra={"params": node.params}
            )
        except SymbolAlreadyDeclared as e:
            self._error(str(e), node.line)

        self.symtab.enter_scope()
        for param in node.params:
            try:
                self.symtab.declare(param, "variable", node.line)
            except SymbolAlreadyDeclared as e:
                self._error(str(e), node.line)

        self.function_depth += 1
        for stmt in node.body:
            self._visit_stmt(stmt)
        self.function_depth -= 1

        self.symtab.exit_scope()

    def _visit_func_call(self, node):
        sym = self.symtab.lookup(node.name)
        if sym is None:
            self._error(f"Call to undeclared function '{node.name}'", node.line)
        elif sym.kind != "function":
            self._error(f"'{node.name}' is not a function", node.line)
        else:
            expected = len(sym.extra.get("params", []))
            got = len(node.args)
            if expected != got:
                self._error(
                    f"Function '{node.name}' expects {expected} argument(s), got {got}",
                    node.line,
                )
        for arg in node.args:
            self._visit_expr(arg)

    def _visit_return(self, node):
        if self.function_depth == 0:
            self._error("RETURN used outside of a function", node.line)
        if node.expr is not None:
            self._visit_expr(node.expr)

    # ---------- music statements ----------

    def _visit_play(self, node):
        self._check_note(node.note, node.line)
        self._check_duration(node.duration, node.line)

    def _visit_rest(self, node):
        self._check_duration(node.duration, node.line)

    def _visit_tempo(self, node):
        self._visit_expr(node.expr)
        value = self._const_value(node.expr)
        if value is not None and value <= 0:
            self._error(f"TEMPO must be positive, got {value}", node.line)

    def _visit_instrument(self, node):
        if not is_valid_instrument(node.name):
            self._error(
                f"Unknown instrument '{node.name}'. "
                f"Valid options: {', '.join(sorted(VALID_INSTRUMENTS))}",
                node.line,
            )
        else:
            canonical = canonicalize_instrument(node.name)
            if canonical:
                node.name = canonical

    def _visit_track(self, node):
        try:
            self.symtab.declare(node.name, "track", node.line)
        except SymbolAlreadyDeclared as e:
            self._error(str(e), node.line)
        self._visit_block(node.body)

    def _visit_parallel(self, node):
        for track in node.tracks:
            self._visit_track(track)

    # ---------- shared helpers ----------

    def _check_note(self, value, line):
        """A note is valid if it matches the note pattern (e.g. C4, D#5),
        OR if it's a recognized General MIDI percussion name (e.g. Kick, Snare, HiHat),
        OR if it's a variable that has already been declared."""
        if NOTE_PATTERN.match(value):
            return
        if self.symtab.is_declared(value):
            return
        if get_percussion_note(value) is not None:
            return
        self._error(
            f"'{value}' is not a valid note (e.g. C4, D#5) "
            f"and is not a declared variable",
            line,
        )

    def _check_duration(self, value, line):
        """A duration is valid if it's one of the known duration words,
        OR if it's a variable that has already been declared."""
        if value in DURATIONS:
            return
        if self.symtab.is_declared(value):
            return
        self._error(
            f"'{value}' is not a valid duration "
            f"(whole/half/quarter/eighth/sixteenth) and is not a declared variable",
            line,
        )


if __name__ == "__main__":
    from lexer import Lexer
    from parser import Parser

    sample = """
    TEMPO 120;
    INSTRUMENT Piano;

    FUNCTION Riff(note, len)
        PLAY note len;
    ENDFUNCTION

    LET x = 4;
    IF x > 2 THEN
        PLAY C4 quarter;
    ELSE
        PLAY D4 quarter;
    ENDIF

    FOR i = 1 TO 3
        PLAY G4 whole;
    ENDFOR

    PLAY i whole;
    """

    tokens, lex_errors = Lexer(sample).tokenize()
    ast, parse_errors = Parser(tokens).parse()
    print("Lex errors:", lex_errors)
    print("Parse errors:", parse_errors)

    analyzer = SemanticAnalyzer()
    sem_errors = analyzer.analyze(ast)
    print("Semantic errors:")
    for e in sem_errors:
        print(" ", e)