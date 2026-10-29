"""
tokens.py
Defines Token and TokenType for SymphonyLang's lexer.
"""

from enum import Enum, auto


class TokenType(Enum):
    # Literals
    NUMBER = auto()
    IDENTIFIER = auto()
    STRING = auto()
    NOTE_LITERAL = auto()
    DURATION_LITERAL = auto()

    # Keywords
    LET = auto()
    IF = auto()
    THEN = auto()
    ELSE = auto()
    ENDIF = auto()
    FOR = auto()
    TO = auto()
    ENDFOR = auto()
    FUNCTION = auto()
    ENDFUNCTION = auto()
    CALL = auto()
    RETURN = auto()
    PLAY = auto()
    REST = auto()
    TEMPO = auto()
    INSTRUMENT = auto()
    TRACK = auto()
    ENDTRACK = auto()
    PARALLEL = auto()
    ENDPARALLEL = auto()
    REPEAT = auto()
    ENDREPEAT = auto()
    INCLUDE = auto()

    # Operators
    PLUS = auto()
    MINUS = auto()
    STAR = auto()
    SLASH = auto()
    ASSIGN = auto()          # =
    LT = auto()               # <
    GT = auto()               # >
    LE = auto()                # <=
    GE = auto()                # >=
    EQ = auto()                 # ==
    NE = auto()                 # !=

    # Punctuation
    LPAREN = auto()
    RPAREN = auto()
    COMMA = auto()
    SEMICOLON = auto()

    # Special
    EOF = auto()


KEYWORDS = {
    "LET": TokenType.LET,
    "IF": TokenType.IF,
    "THEN": TokenType.THEN,
    "ELSE": TokenType.ELSE,
    "ENDIF": TokenType.ENDIF,
    "FOR": TokenType.FOR,
    "TO": TokenType.TO,
    "ENDFOR": TokenType.ENDFOR,
    "FUNCTION": TokenType.FUNCTION,
    "ENDFUNCTION": TokenType.ENDFUNCTION,
    "CALL": TokenType.CALL,
    "RETURN": TokenType.RETURN,
    "PLAY": TokenType.PLAY,
    "REST": TokenType.REST,
    "TEMPO": TokenType.TEMPO,
    "INSTRUMENT": TokenType.INSTRUMENT,
    "TRACK": TokenType.TRACK,
    "ENDTRACK": TokenType.ENDTRACK,
    "PARALLEL": TokenType.PARALLEL,
    "ENDPARALLEL": TokenType.ENDPARALLEL,
    "REPEAT": TokenType.REPEAT,
    "ENDREPEAT": TokenType.ENDREPEAT,
    "INCLUDE": TokenType.INCLUDE,
}

DURATIONS = {"whole", "half", "quarter", "eighth", "sixteenth"}


class Token:
    __slots__ = ("type", "value", "line", "column")

    def __init__(self, type_: TokenType, value, line: int, column: int):
        self.type = type_
        self.value = value
        self.line = line
        self.column = column

    def __repr__(self):
        return f"Token({self.type.name}, {self.value!r}, line={self.line}, col={self.column})"