"""
ast_nodes.py
Defines the AST (Abstract Syntax Tree) node types for SymphonyLang.

These are simple data-holding classes - no logic here, just shapes
that represent each piece of a program. The Parser builds these,
and later stages (semantic analyzer, IR generator) read them.
"""


class Node:
    """Base class - every AST node inherits from this."""
    pass


# ---------- Program ----------

class Program(Node):
    def __init__(self, statements):
        self.statements = statements  # list of Node

    def __repr__(self):
        return f"Program({len(self.statements)} statements)"


# ---------- Variables & Expressions ----------

class VarDecl(Node):
    def __init__(self, name, expr, line):
        self.name = name
        self.expr = expr
        self.line = line

    def __repr__(self):
        return f"VarDecl({self.name} = {self.expr})"


class Assign(Node):
    def __init__(self, name, expr, line):
        self.name = name
        self.expr = expr
        self.line = line

    def __repr__(self):
        return f"Assign({self.name} = {self.expr})"


class BinaryExpr(Node):
    def __init__(self, left, op, right, line):
        self.left = left
        self.op = op          # '+', '-', '*', '/', '<', '>', etc.
        self.right = right
        self.line = line

    def __repr__(self):
        return f"BinaryExpr({self.left} {self.op} {self.right})"


class UnaryExpr(Node):
    """Represents a unary operation: a single '-' directly in front of a value,
    e.g. -50 or -x. Different from BinaryExpr, which needs two operands."""
    def __init__(self, op, operand, line):
        self.op = op            # currently only '-'
        self.operand = operand  # the Node being negated
        self.line = line

    def __repr__(self):
        return f"UnaryExpr({self.op}{self.operand})"


class NumberLiteral(Node):
    def __init__(self, value, line):
        self.value = value
        self.line = line

    def __repr__(self):
        return f"Number({self.value})"


class Identifier(Node):
    def __init__(self, name, line):
        self.name = name
        self.line = line

    def __repr__(self):
        return f"Identifier({self.name})"

class NoteLiteral(Node):
    def __init__(self, value, line):
        self.value = value
        self.line = line

    def __repr__(self):
        return f"Note({self.value})"


class DurationLiteral(Node):
    def __init__(self, value, line):
        self.value = value
        self.line = line

    def __repr__(self):
        return f"Duration({self.value})"


# ---------- Control Flow ----------

class IfStmt(Node):
    def __init__(self, condition, then_body, else_body, line):
        self.condition = condition
        self.then_body = then_body    # list of Node
        self.else_body = else_body    # list of Node or None
        self.line = line

    def __repr__(self):
        return f"IfStmt(cond={self.condition})"


class ForStmt(Node):
    def __init__(self, var_name, start_expr, end_expr, body, line):
        self.var_name = var_name
        self.start_expr = start_expr
        self.end_expr = end_expr
        self.body = body              # list of Node
        self.line = line

    def __repr__(self):
        return f"ForStmt({self.var_name} = {self.start_expr} TO {self.end_expr})"


class RepeatStmt(Node):
    def __init__(self, count_expr, body, line):
        self.count_expr = count_expr
        self.body = body
        self.line = line

    def __repr__(self):
        return f"RepeatStmt(count={self.count_expr})"


# ---------- Functions ----------

class FuncDecl(Node):
    def __init__(self, name, params, body, line):
        self.name = name
        self.params = params          # list of str
        self.body = body              # list of Node
        self.line = line

    def __repr__(self):
        return f"FuncDecl({self.name}({', '.join(self.params)}))"


class FuncCall(Node):
    def __init__(self, name, args, line):
        self.name = name
        self.args = args              # list of Node (expressions)
        self.line = line

    def __repr__(self):
        return f"FuncCall({self.name}({self.args}))"


class ReturnStmt(Node):
    def __init__(self, expr, line):
        self.expr = expr              # Node or None
        self.line = line

    def __repr__(self):
        return f"ReturnStmt({self.expr})"


# ---------- Music Statements ----------

class PlayStmt(Node):
    def __init__(self, note, duration, line):
        self.note = note               # str (note literal) or Identifier
        self.duration = duration       # str (duration literal) or Identifier
        self.line = line

    def __repr__(self):
        return f"PlayStmt({self.note}, {self.duration})"


class RestStmt(Node):
    def __init__(self, duration, line):
        self.duration = duration
        self.line = line

    def __repr__(self):
        return f"RestStmt({self.duration})"


class TempoStmt(Node):
    def __init__(self, expr, line):
        self.expr = expr
        self.line = line

    def __repr__(self):
        return f"TempoStmt({self.expr})"


class InstrumentStmt(Node):
    def __init__(self, name, line):
        self.name = name
        self.line = line

    def __repr__(self):
        return f"InstrumentStmt({self.name})"


class TrackStmt(Node):
    def __init__(self, name, body, line):
        self.name = name
        self.body = body               # list of Node
        self.line = line

    def __repr__(self):
        return f"TrackStmt({self.name})"


class ParallelBlock(Node):
    """A group of TRACK blocks explicitly declared to play at the same time.
    Every track inside here MUST get a different MIDI channel - this is
    exactly what the channel allocator uses to know which tracks 'conflict'."""
    def __init__(self, tracks, line):
        self.tracks = tracks   # list of TrackStmt
        self.line = line

    def __repr__(self):
        names = [t.name for t in self.tracks]
        return f"ParallelBlock({names})"


class IncludeStmt(Node):
    def __init__(self, filename, line):
        self.filename = filename
        self.line = line

    def __repr__(self):
        return f"IncludeStmt({self.filename})"