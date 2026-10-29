import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from lexer import Lexer
from parser import Parser
from semantic_analyzer import SemanticAnalyzer


def validate_program(source):
    tokens, lex_errors = Lexer(source).tokenize()

    if lex_errors:
        return False, "LEXER"

    ast, parse_errors = Parser(tokens).parse()

    if parse_errors:
        return False, "PARSER"

    semantic_errors = SemanticAnalyzer().analyze(ast)

    if semantic_errors:
        return False, "SEMANTIC"

    return True, "OK"


def validate_dataset(filename):
    total = 0
    passed = 0
    failed = 0

    with open(filename, "r", encoding="utf-8") as f:
        for line_number, line in enumerate(f, 1):
            example = json.loads(line)

            source = example["output"]

            total += 1

            valid, stage = validate_program(source)

            if valid:
                passed += 1
                print(f"Example {line_number}: PASS")
            else:
                failed += 1
                print(f"Example {line_number}: FAIL ({stage})")
                print(source)

    print()
    print("=" * 40)
    print(f"Total : {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print("=" * 40)


if __name__ == "__main__":
    filename = "dataset_v1.jsonl"

    if len(sys.argv) >= 2:
        filename = sys.argv[1]

    validate_dataset(filename)