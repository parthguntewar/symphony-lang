import glob
import os

from lexer import Lexer
from parser import Parser
from semantic_analyzer import SemanticAnalyzer


def check_invalid(path):
    with open(path) as f:
        source = f.read()

    print(f"\n{'=' * 60}")
    print(f"TEST: {os.path.basename(path)}")
    print(f"{'=' * 60}")

    try:
        # Lexer
        tokens, lex_errors = Lexer(source).tokenize()

        if lex_errors:
            print("Result: PASS")
            print("  Lexer rejected the program:")
            for error in lex_errors:
                print(f"    {error}")
            return True

        # Parser
        ast, parse_errors = Parser(tokens).parse()

        if parse_errors:
            print("Result: PASS")
            print("  Parser rejected the program:")
            for error in parse_errors:
                print(f"    {error}")
            return True

        # Semantic analysis
        sem_errors = SemanticAnalyzer().analyze(ast)

        if sem_errors:
            print("Result: PASS")
            print("  Semantic analyzer rejected the program:")
            for error in sem_errors:
                print(f"    {error}")
            return True

        # No stage rejected it
        print("Result: FAIL")
        print("  Invalid program was accepted.")
        return False

    except Exception as e:
        print("Result: ERROR")
        print(f"  Unexpected compiler exception: {type(e).__name__}: {e}")
        return False


def main():
    paths = sorted(glob.glob("../testcases/invalid/*.sym"))

    if not paths:
        print("No invalid test files found.")
        return 1

    passed = 0
    failed = 0

    for path in paths:
        if check_invalid(path):
            passed += 1
        else:
            failed += 1

    print(f"\n{'=' * 60}")
    print("INVALID TEST SUMMARY")
    print(f"{'=' * 60}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Total : {len(paths)}")

    if failed == 0:
        print("\n✅ ALL INVALID TESTS PASSED")
        return 0

    print("\n❌ SOME INVALID TESTS FAILED")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
