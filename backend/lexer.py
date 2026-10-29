"""
lexer.py
Hand-written lexer (tokenizer) for SymphonyLang.

Converts raw source text into a stream of Token objects.
Reports lexical errors with line/column info instead of crashing,
so multiple errors can be collected in one pass.
"""

import re
from tokens import Token, TokenType, KEYWORDS, DURATIONS


class LexError:
    def __init__(self, message: str, line: int, column: int):
        self.message = message
        self.line = line
        self.column = column

    def __repr__(self):
        return f"LexError(line={self.line}, col={self.column}): {self.message}"


NOTE_PATTERN = re.compile(r"^[A-G](#|b)?\d$")


class Lexer:
    def __init__(self, source: str):
        self.source = source
        self.pos = 0
        self.line = 1
        self.col = 1
        self.tokens = []
        self.errors = []

    # ---------- low-level helpers ----------

    def _peek(self, offset=0):
        idx = self.pos + offset
        if idx < len(self.source):
            return self.source[idx]
        return "\0"

    def _advance(self):
        ch = self.source[self.pos]
        self.pos += 1
        if ch == "\n":
            self.line += 1
            self.col = 1
        else:
            self.col += 1
        return ch

    def _match(self, expected):
        if self._peek() == expected:
            self._advance()
            return True
        return False

    def _add(self, type_, value, start_line, start_col):
        self.tokens.append(Token(type_, value, start_line, start_col))

    # ---------- main loop ----------

    def tokenize(self):
        while self.pos < len(self.source):
            ch = self._peek()

            if ch in " \t\r\n":
                self._advance()
                continue

            if ch == "#":
                self._skip_comment()
                continue

            if ch == '"':
                self._read_string()
                continue

            if ch.isdigit():
                self._read_number_or_note()
                continue

            if ch.isalpha() or ch == "_":
                self._read_identifier_keyword_note_duration()
                continue

            self._read_operator_or_punct()

        self.tokens.append(Token(TokenType.EOF, None, self.line, self.col))
        return self.tokens, self.errors

    # ---------- token readers ----------

    def _skip_comment(self):
        while self._peek() != "\n" and self._peek() != "\0":
            self._advance()

    def _read_string(self):
        start_line, start_col = self.line, self.col
        self._advance()  # consume opening quote
        chars = []
        while self._peek() != '"' and self._peek() != "\0":
            chars.append(self._advance())
        if self._peek() == "\0":
            self.errors.append(LexError("Unterminated string literal", start_line, start_col))
            return
        self._advance()  # consume closing quote
        self._add(TokenType.STRING, "".join(chars), start_line, start_col)

    def _read_number_or_note(self):
        start_line, start_col = self.line, self.col
        chars = []
        while self._peek().isdigit():
            chars.append(self._advance())
        self._add(TokenType.NUMBER, int("".join(chars)), start_line, start_col)

    def _read_identifier_keyword_note_duration(self):
        start_line, start_col = self.line, self.col
        chars = [self._advance()]
        while self._peek().isalnum() or self._peek() == "_" or self._peek() == "#":
            # allow '#' only if it directly follows a note letter (handled below)
            if self._peek() == "#" and not (len(chars) == 1 and chars[0] in "ABCDEFG"):
                break
            chars.append(self._advance())
        text = "".join(chars)

        if text in KEYWORDS:
            self._add(KEYWORDS[text], text, start_line, start_col)
        elif text in DURATIONS:
            self._add(TokenType.DURATION_LITERAL, text, start_line, start_col)
        elif NOTE_PATTERN.match(text):
            self._add(TokenType.NOTE_LITERAL, text, start_line, start_col)
        else:
            self._add(TokenType.IDENTIFIER, text, start_line, start_col)

    def _read_operator_or_punct(self):
        start_line, start_col = self.line, self.col
        ch = self._advance()

        simple = {
            "+": TokenType.PLUS,
            "-": TokenType.MINUS,
            "*": TokenType.STAR,
            "/": TokenType.SLASH,
            "(": TokenType.LPAREN,
            ")": TokenType.RPAREN,
            ",": TokenType.COMMA,
            ";": TokenType.SEMICOLON,
        }

        if ch in simple:
            self._add(simple[ch], ch, start_line, start_col)
            return

        if ch == "=":
            if self._match("="):
                self._add(TokenType.EQ, "==", start_line, start_col)
            else:
                self._add(TokenType.ASSIGN, "=", start_line, start_col)
            return

        if ch == "<":
            if self._match("="):
                self._add(TokenType.LE, "<=", start_line, start_col)
            else:
                self._add(TokenType.LT, "<", start_line, start_col)
            return

        if ch == ">":
            if self._match("="):
                self._add(TokenType.GE, ">=", start_line, start_col)
            else:
                self._add(TokenType.GT, ">", start_line, start_col)
            return

        if ch == "!":
            if self._match("="):
                self._add(TokenType.NE, "!=", start_line, start_col)
            else:
                self.errors.append(LexError(f"Unexpected character '!'", start_line, start_col))
            return

        self.errors.append(LexError(f"Unexpected character '{ch}'", start_line, start_col))


if __name__ == "__main__":
    sample = '''
    TEMPO 120
    INSTRUMENT Piano
    LET x = 4
    IF x > 2 THEN
        PLAY C4 quarter
    ELSE
        PLAY D4 quarter
    ENDIF
    '''
    lx = Lexer(sample)
    toks, errs = lx.tokenize()
    for t in toks:
        print(t)
    print("Errors:", errs)