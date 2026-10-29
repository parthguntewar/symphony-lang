"""
parser.py
Hand-written recursive-descent parser for SymphonyLang.

Takes the token list from the Lexer and builds an AST (see ast_nodes.py).
Uses panic-mode error recovery: on a syntax error, it reports the error
and skips ahead to the next likely-safe statement boundary instead of
stopping immediately, so multiple errors can surface in one run.
"""

from tokens import TokenType
from ast_nodes import (
    Program, VarDecl, Assign, BinaryExpr, UnaryExpr,
    NumberLiteral, Identifier, NoteLiteral, DurationLiteral,
    IfStmt, ForStmt, RepeatStmt, FuncDecl, FuncCall, ReturnStmt,
    PlayStmt, RestStmt, TempoStmt, InstrumentStmt, TrackStmt, ParallelBlock,
    IncludeStmt,
)


class ParseError:
    def __init__(self, message, line, column):
        self.message = message
        self.line = line
        self.column = column

    def __repr__(self):
        return f"ParseError(line={self.line}, col={self.column}): {self.message}"


# Tokens that can safely start a new statement - used to recover after an error.
STATEMENT_START = {
    TokenType.LET, TokenType.IF, TokenType.FOR, TokenType.FUNCTION,
    TokenType.CALL, TokenType.PLAY, TokenType.REST, TokenType.TEMPO,
    TokenType.INSTRUMENT, TokenType.TRACK, TokenType.REPEAT,
    TokenType.INCLUDE, TokenType.RETURN, TokenType.IDENTIFIER,
    TokenType.PARALLEL,
}

# Tokens that end a block - parsing loops should stop here.
BLOCK_ENDERS = {
    TokenType.ENDIF, TokenType.ELSE, TokenType.ENDFOR, TokenType.ENDFUNCTION,
    TokenType.ENDTRACK, TokenType.ENDREPEAT, TokenType.ENDPARALLEL, TokenType.EOF,
}


class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0
        self.errors = []

    # ---------- low-level helpers ----------

    def _peek(self, offset=0):
        idx = self.pos + offset
        if idx < len(self.tokens):
            return self.tokens[idx]
        return self.tokens[-1]  # EOF

    def _advance(self):
        tok = self.tokens[self.pos]
        if tok.type != TokenType.EOF:
            self.pos += 1
        return tok

    def _check(self, type_):
        return self._peek().type == type_

    def _match(self, *types):
        if self._peek().type in types:
            return self._advance()
        return None

    def _expect(self, type_, message):
        if self._check(type_):
            return self._advance()
        tok = self._peek()
        self.errors.append(ParseError(message, tok.line, tok.column))
        return None

    def _synchronize(self):
        """Panic-mode recovery: skip tokens until a likely statement boundary."""
        while not self._check(TokenType.EOF):
            if self._peek().type in STATEMENT_START or self._peek().type in BLOCK_ENDERS:
                return
            self._advance()

    # ---------- entry point ----------

    def parse(self):
        statements = []
        while not self._check(TokenType.EOF):
            stmt = self._parse_statement()
            if stmt is not None:
                statements.append(stmt)
        return Program(statements), self.errors

    # ---------- statements ----------

    def _parse_statement(self):
        tok = self._peek()

        try:
            if tok.type == TokenType.LET:
                return self._parse_var_decl()
            if tok.type == TokenType.IF:
                return self._parse_if()
            if tok.type == TokenType.FOR:
                return self._parse_for()
            if tok.type == TokenType.REPEAT:
                return self._parse_repeat()
            if tok.type == TokenType.FUNCTION:
                return self._parse_func_decl()
            if tok.type == TokenType.CALL:
                node = self._parse_func_call()
                self._expect(TokenType.SEMICOLON, "Expected ';' after function call")
                return node
            if tok.type == TokenType.RETURN:
                return self._parse_return()
            if tok.type == TokenType.PLAY:
                return self._parse_play()
            if tok.type == TokenType.REST:
                return self._parse_rest()
            if tok.type == TokenType.TEMPO:
                return self._parse_tempo()
            if tok.type == TokenType.INSTRUMENT:
                return self._parse_instrument()
            if tok.type == TokenType.TRACK:
                return self._parse_track()
            if tok.type == TokenType.PARALLEL:
                return self._parse_parallel()
            if tok.type == TokenType.INCLUDE:
                return self._parse_include()
            if tok.type == TokenType.IDENTIFIER:
                return self._parse_assign()

            # Nothing matched -> unexpected token
            self.errors.append(ParseError(
                f"Unexpected token '{tok.value}'", tok.line, tok.column))
            self._advance()
            self._synchronize()
            return None

        except _ParseAbort:
            self._synchronize()
            return None

    def _parse_block(self, *end_types):
        """Parse statements until one of end_types is seen (not consumed)."""
        statements = []
        while self._peek().type not in end_types and not self._check(TokenType.EOF):
            stmt = self._parse_statement()
            if stmt is not None:
                statements.append(stmt)
        return statements

    # ---------- variables ----------

    def _parse_var_decl(self):
        line = self._peek().line
        self._advance()  # LET
        name_tok = self._expect(TokenType.IDENTIFIER, "Expected variable name after LET")
        if name_tok is None:
            raise _ParseAbort()
        self._expect(TokenType.ASSIGN, "Expected '=' in variable declaration")
        expr = self._parse_expression()
        self._expect(TokenType.SEMICOLON, "Expected ';' after variable declaration")
        return VarDecl(name_tok.value, expr, line)

    def _parse_assign(self):
        name_tok = self._advance()  # IDENTIFIER
        self._expect(TokenType.ASSIGN, "Expected '=' in assignment")
        expr = self._parse_expression()
        self._expect(TokenType.SEMICOLON, "Expected ';' after assignment")
        return Assign(name_tok.value, expr, name_tok.line)

    # ---------- expressions (precedence climbing) ----------

    def _parse_expression(self):
        return self._parse_comparison()

    def _parse_comparison(self):
        left = self._parse_add_sub()
        if self._peek().type in (TokenType.LT, TokenType.GT, TokenType.LE,
                                  TokenType.GE, TokenType.EQ, TokenType.NE):
            op_tok = self._advance()
            right = self._parse_add_sub()
            return BinaryExpr(left, op_tok.value, right, op_tok.line)
        return left

    def _parse_add_sub(self):
        left = self._parse_mul_div()
        while self._peek().type in (TokenType.PLUS, TokenType.MINUS):
            op_tok = self._advance()
            right = self._parse_mul_div()
            left = BinaryExpr(left, op_tok.value, right, op_tok.line)
        return left

    def _parse_mul_div(self):
        left = self._parse_unary()
        while self._peek().type in (TokenType.STAR, TokenType.SLASH):
            op_tok = self._advance()
            right = self._parse_unary()
            left = BinaryExpr(left, op_tok.value, right, op_tok.line)
        return left

    def _parse_unary(self):
        """Handles a leading '-' with nothing before it, e.g. -50 or -x.
        This is different from subtraction (10 - 3), which is handled
        in _parse_add_sub instead."""
        tok = self._peek()
        if tok.type == TokenType.MINUS:
            self._advance()
            operand = self._parse_unary()  # allows chaining, e.g. --x (rare but harmless)
            return UnaryExpr("-", operand, tok.line)
        return self._parse_factor()

    def _parse_factor(self):
        tok = self._peek()
        if tok.type == TokenType.NUMBER:
            self._advance()
            return NumberLiteral(tok.value, tok.line)

        if tok.type == TokenType.NOTE_LITERAL:
            self._advance()
            return NoteLiteral(tok.value, tok.line)

        if tok.type == TokenType.DURATION_LITERAL:
            self._advance()
            return DurationLiteral(tok.value, tok.line)

        if tok.type == TokenType.IDENTIFIER:
            self._advance()
            return Identifier(tok.value, tok.line)
        
        if tok.type == TokenType.LPAREN:
            self._advance()
            expr = self._parse_expression()
            self._expect(TokenType.RPAREN, "Expected ')' after expression")
            return expr
        self.errors.append(ParseError(
            f"Expected an expression, found '{tok.value}'", tok.line, tok.column))
        raise _ParseAbort()

    # ---------- control flow ----------

    def _parse_if(self):
        line = self._peek().line
        self._advance()  # IF
        condition = self._parse_expression()
        self._expect(TokenType.THEN, "Expected 'THEN' after IF condition")
        then_body = self._parse_block(TokenType.ELSE, TokenType.ENDIF)
        else_body = None
        if self._match(TokenType.ELSE):
            else_body = self._parse_block(TokenType.ENDIF)
        self._expect(TokenType.ENDIF, "Expected 'ENDIF' to close IF block")
        return IfStmt(condition, then_body, else_body, line)

    def _parse_for(self):
        line = self._peek().line
        self._advance()  # FOR
        name_tok = self._expect(TokenType.IDENTIFIER, "Expected loop variable name after FOR")
        self._expect(TokenType.ASSIGN, "Expected '=' after loop variable")
        start_expr = self._parse_expression()
        self._expect(TokenType.TO, "Expected 'TO' in FOR loop range")
        end_expr = self._parse_expression()
        body = self._parse_block(TokenType.ENDFOR)
        self._expect(TokenType.ENDFOR, "Expected 'ENDFOR' to close FOR loop")
        var_name = name_tok.value if name_tok else "?"
        return ForStmt(var_name, start_expr, end_expr, body, line)

    def _parse_repeat(self):
        line = self._peek().line
        self._advance()  # REPEAT
        count_expr = self._parse_expression()
        body = self._parse_block(TokenType.ENDREPEAT)
        self._expect(TokenType.ENDREPEAT, "Expected 'ENDREPEAT' to close REPEAT block")
        return RepeatStmt(count_expr, body, line)

    # ---------- functions ----------

    def _parse_func_decl(self):
        line = self._peek().line
        self._advance()  # FUNCTION
        name_tok = self._expect(TokenType.IDENTIFIER, "Expected function name after FUNCTION")
        self._expect(TokenType.LPAREN, "Expected '(' after function name")
        params = []
        if not self._check(TokenType.RPAREN):
            p = self._expect(TokenType.IDENTIFIER, "Expected parameter name")
            if p:
                params.append(p.value)
            while self._match(TokenType.COMMA):
                p = self._expect(TokenType.IDENTIFIER, "Expected parameter name after ','")
                if p:
                    params.append(p.value)
        self._expect(TokenType.RPAREN, "Expected ')' after parameter list")
        body = self._parse_block(TokenType.ENDFUNCTION)
        self._expect(TokenType.ENDFUNCTION, "Expected 'ENDFUNCTION' to close function")
        name = name_tok.value if name_tok else "?"
        return FuncDecl(name, params, body, line)

    def _parse_func_call(self):
        line = self._peek().line
        self._advance()  # CALL
        name_tok = self._expect(TokenType.IDENTIFIER, "Expected function name after CALL")
        self._expect(TokenType.LPAREN, "Expected '(' after function name")
        args = []
        if not self._check(TokenType.RPAREN):
            args.append(self._parse_expression())
            while self._match(TokenType.COMMA):
                args.append(self._parse_expression())
        self._expect(TokenType.RPAREN, "Expected ')' after arguments")
        name = name_tok.value if name_tok else "?"
        return FuncCall(name, args, line)

    def _parse_return(self):
        line = self._peek().line
        self._advance()  # RETURN
        expr = None
        if not self._check(TokenType.SEMICOLON):
            expr = self._parse_expression()
        self._expect(TokenType.SEMICOLON, "Expected ';' after RETURN")
        return ReturnStmt(expr, line)

    # ---------- music statements ----------

    def _parse_play(self):
        line = self._peek().line
        self._advance()  # PLAY
        note_tok = self._match(TokenType.NOTE_LITERAL, TokenType.IDENTIFIER)
        if note_tok is None:
            tok = self._peek()
            self.errors.append(ParseError(
                "Expected a note (e.g. C4) or variable after PLAY", tok.line, tok.column))
            raise _ParseAbort()
        dur_tok = self._match(TokenType.DURATION_LITERAL, TokenType.IDENTIFIER)
        if dur_tok is None:
            tok = self._peek()
            self.errors.append(ParseError(
                "Expected a duration (e.g. quarter) or variable after note", tok.line, tok.column))
            raise _ParseAbort()
        self._expect(TokenType.SEMICOLON, "Expected ';' after PLAY statement")
        return PlayStmt(note_tok.value, dur_tok.value, line)

    def _parse_rest(self):
        line = self._peek().line
        self._advance()  # REST
        dur_tok = self._match(TokenType.DURATION_LITERAL, TokenType.IDENTIFIER)
        if dur_tok is None:
            tok = self._peek()
            self.errors.append(ParseError(
                "Expected a duration after REST", tok.line, tok.column))
            raise _ParseAbort()
        self._expect(TokenType.SEMICOLON, "Expected ';' after REST statement")
        return RestStmt(dur_tok.value, line)

    def _parse_tempo(self):
        line = self._peek().line
        self._advance()  # TEMPO
        expr = self._parse_expression()
        self._expect(TokenType.SEMICOLON, "Expected ';' after TEMPO statement")
        return TempoStmt(expr, line)

    def _parse_instrument(self):
        line = self._peek().line
        self._advance()  # INSTRUMENT
        name_tok = self._expect(TokenType.IDENTIFIER, "Expected instrument name")
        self._expect(TokenType.SEMICOLON, "Expected ';' after INSTRUMENT statement")
        name = name_tok.value if name_tok else "?"
        return InstrumentStmt(name, line)

    def _parse_track(self):
        line = self._peek().line
        self._advance()  # TRACK
        name_tok = self._expect(TokenType.IDENTIFIER, "Expected track name")
        body = self._parse_block(TokenType.ENDTRACK)
        self._expect(TokenType.ENDTRACK, "Expected 'ENDTRACK' to close TRACK block")
        name = name_tok.value if name_tok else "?"
        return TrackStmt(name, body, line)

    def _parse_parallel(self):
        line = self._peek().line
        self._advance()  # PARALLEL
        tracks = []
        while not self._check(TokenType.ENDPARALLEL) and not self._check(TokenType.EOF):
            if self._check(TokenType.TRACK):
                tracks.append(self._parse_track())
            else:
                tok = self._peek()
                self.errors.append(ParseError(
                    "Only TRACK blocks are allowed inside PARALLEL",
                    tok.line, tok.column))
                self._advance()
                self._synchronize()
        self._expect(TokenType.ENDPARALLEL, "Expected 'ENDPARALLEL' to close PARALLEL block")
        return ParallelBlock(tracks, line)

    def _parse_include(self):
        line = self._peek().line
        self._advance()  # INCLUDE
        str_tok = self._expect(TokenType.STRING, "Expected a filename string after INCLUDE")
        self._expect(TokenType.SEMICOLON, "Expected ';' after INCLUDE statement")
        filename = str_tok.value if str_tok else "?"
        return IncludeStmt(filename, line)


class _ParseAbort(Exception):
    """Internal signal used to trigger panic-mode recovery for the current statement."""
    pass


if __name__ == "__main__":
    from lexer import Lexer

    sample = """
    TEMPO 120
    INSTRUMENT Piano

    FUNCTION Riff(note, len)
        PLAY note len
    ENDFUNCTION

    LET x = 4
    IF x > 2 THEN
        CALL Riff(C4, quarter)
    ELSE
        PLAY D4 quarter
    ENDIF

    FOR i = 1 TO 3
        PLAY G4 whole
    ENDFOR
    """

    tokens, lex_errors = Lexer(sample).tokenize()
    print("Lex errors:", lex_errors)

    ast, parse_errors = Parser(tokens).parse()
    print("Parse errors:", parse_errors)
    print()
    for stmt in ast.statements:
        print(stmt)