import json
from pathlib import Path

from backend.parser import ParserClarification, ParserError, parse_transactions


CASES_PATH = Path(__file__).with_name("parser_cases.json")


def main():
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    passed = 0
    for index, case in enumerate(cases, start=1):
        transcript = case["transcript"]
        expects_clarification = case.get("clarification", False)
        try:
            actual = parse_transactions(transcript)
            if expects_clarification:
                raise AssertionError("expected a clarification question")
            expected = case["expected"]
            stable_fields = ("person", "amount", "type")
            comparable = [
                {field: transaction[field] for field in stable_fields}
                for transaction in actual
            ]
            normalized_expected = [
                {field: transaction[field] for field in stable_fields}
                for transaction in expected
            ]
            if comparable != normalized_expected:
                raise AssertionError(f"expected {normalized_expected!r}, got {comparable!r}")
            if any(not transaction["note"].strip() for transaction in actual):
                raise AssertionError("each transaction must include a non-empty note")
            passed += 1
            print(f"PASS {index:02}: {transcript}")
        except ParserClarification as exc:
            if expects_clarification and exc.question.strip():
                passed += 1
                print(f"PASS {index:02}: clarification: {exc.question}")
            else:
                print(f"FAIL {index:02}: unexpected clarification: {exc.question}")
        except (ParserError, AssertionError, KeyError, TypeError) as exc:
            print(f"FAIL {index:02}: {exc}")

    total = len(cases)
    print(f"Pass rate: {passed}/{total} ({passed / total:.0%})")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())