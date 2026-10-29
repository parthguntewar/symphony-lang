"""
symbol_table.py
Tracks declared names (variables, functions, instruments) and the scope
they belong to. Supports nested scopes: e.g. a variable declared inside
a function or IF/FOR block is only visible inside that block.

Think of it as a stack of dictionaries. When we enter a new block
(function body, for-loop body, etc.) we push a new empty scope.
When we leave that block, we pop it - anything declared inside is
forgotten. Looking up a name searches from the innermost scope
outward to the global scope.
"""


class SymbolAlreadyDeclared(Exception):
    pass


class Symbol:
    """Represents one declared name: a variable, function, or instrument."""
    def __init__(self, name, kind, line, extra=None):
        self.name = name
        self.kind = kind          # 'variable' | 'function' | 'instrument' | 'track'
        self.line = line          # where it was declared
        self.extra = extra or {}  # e.g. {'params': [...]} for functions

    def __repr__(self):
        return f"Symbol({self.name}, kind={self.kind}, line={self.line})"


class SymbolTable:
    def __init__(self):
        # Start with one scope: the global scope.
        self.scopes = [{}]

    # ---------- scope management ----------

    def enter_scope(self):
        """Call this when entering a function body, IF block, FOR block, etc."""
        self.scopes.append({})

    def exit_scope(self):
        """Call this when leaving that block."""
        if len(self.scopes) == 1:
            raise RuntimeError("Cannot exit the global scope")
        self.scopes.pop()

    # ---------- declaring names ----------

    def declare(self, name, kind, line, extra=None):
        """
        Add a new symbol to the CURRENT (innermost) scope.
        Raises SymbolAlreadyDeclared if this name already exists
        in the current scope (redeclaration in the same block).
        """
        current = self.scopes[-1]
        if name in current:
            raise SymbolAlreadyDeclared(
                f"'{name}' is already declared in this scope "
                f"(first declared at line {current[name].line})"
            )
        current[name] = Symbol(name, kind, line, extra)

    # ---------- looking up names ----------

    def lookup(self, name):
        """
        Search for a name starting from the innermost scope outward.
        Returns the Symbol if found, or None if it doesn't exist anywhere.
        """
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name]
        return None

    def is_declared(self, name):
        return self.lookup(name) is not None

    def is_declared_in_current_scope(self, name):
        return name in self.scopes[-1]

    # ---------- debugging ----------

    def __repr__(self):
        lines = []
        for depth, scope in enumerate(self.scopes):
            names = ", ".join(scope.keys()) if scope else "(empty)"
            lines.append(f"  Scope[{depth}]: {names}")
        return "SymbolTable(\n" + "\n".join(lines) + "\n)"


if __name__ == "__main__":
    st = SymbolTable()

    # Global scope: declare a variable
    st.declare("x", "variable", line=1)
    print(st)

    # Enter a function's scope
    st.enter_scope()
    st.declare("note", "variable", line=5)
    st.declare("len", "variable", line=5)
    print(st)

    print("Lookup 'note' inside function:", st.lookup("note"))
    print("Lookup 'x' inside function (should find global x):", st.lookup("x"))

    # Leave the function
    st.exit_scope()
    print(st)

    print("Lookup 'note' after leaving function (should be None):", st.lookup("note"))

    # Try declaring 'x' again in global scope -> should fail
    try:
        st.declare("x", "variable", line=10)
    except SymbolAlreadyDeclared as e:
        print("Caught expected error:", e)