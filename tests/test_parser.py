import argparse
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from backend.parser import (
    GeminiProvider,
    ParseResult,
    ParserClarification,
    ParserError,
    ParserProvider,
    parse_fallback,
    parse_transactions,
    parse_with_provider,
    _default_provider,
)


CASES_PATH = Path(__file__).with_name("parser_cases.json")


def _matches_case(parse, case):
    try:
        actual = parse(case["transcript"])
        if case.get("clarification", False):
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
        return True, ""
    except ParserClarification as exc:
        if case.get("clarification", False) and exc.question.strip():
            return True, f"clarification: {exc.question}"
        return False, f"unexpected clarification: {exc.question}"
    except (ParserError, AssertionError, KeyError, TypeError) as exc:
        return False, str(exc)


def _report_path(label, parse, cases):
    passed = 0
    for index, case in enumerate(cases, start=1):
        success, detail = _matches_case(parse, case)
        passed += success
        status = "PASS" if success else "FAIL"
        suffix = f" ({detail})" if detail else ""
        print(f"{label} {status} {index:02}: {case['transcript']}{suffix}")
    total = len(cases)
    rate = passed / total if total else 1
    print(f"{label} pass rate: {passed}/{total} ({rate:.0%})")
    return passed == total


def main():
    argument_parser = argparse.ArgumentParser(description="Evaluate transaction parser paths.")
    argument_parser.add_argument(
        "--path",
        choices=("both", "llm", "fallback"),
        default="both",
        help="Evaluate Gemini, local rules, or both.",
    )
    args = argument_parser.parse_args()
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    successful = True

    if args.path in ("both", "llm"):
        try:
            provider = _default_provider()
        except ParserError as exc:
            print(f"Gemini path unavailable: {exc}")
            print(f"Gemini pass rate: 0/{len(cases)} (unavailable)")
            if args.path == "llm":
                return 1
        else:
            successful = _report_path(
                "Gemini",
                lambda transcript: parse_with_provider(transcript, provider),
                cases,
            ) and successful

    if args.path in ("both", "fallback"):
        successful = _report_path("Fallback", parse_fallback, cases) and successful
    return 0 if successful else 1


class FallbackParserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))

    def test_fallback_corpus(self):
        failed = []
        for index, case in enumerate(self.cases, start=1):
            success, message = _matches_case(parse_fallback, case)
            if not success:
                failed.append(f"{index}: {message}")
        self.assertEqual(failed, [])

    def test_fallback_is_marked_low_confidence(self):
        parsed = parse_fallback("Ramesh ko paanch sau udhaar diya")
        self.assertTrue(parsed.low_confidence)
        self.assertEqual(
            set(parsed[0]),
            {"person", "amount", "type", "note"},
        )

    def test_gemini_provider_requests_json_and_validates_response(self):
        provider = GeminiProvider("test-key", "test-model", 5)
        response = SimpleNamespace(
            text=(
                '{"transactions":[{"person":"Ramesh ji","amount":500,'
                '"type":"credit_given","note":"udhaar diya"}],'
                '"clarification_question":null}'
            )
        )
        with patch.object(
            provider._client.models,
            "generate_content",
            return_value=response,
        ) as generate_content:
            parsed = provider.parse("Ramesh ko paanch sau udhaar diya")

        self.assertEqual(parsed.transactions[0].person, "Ramesh")
        self.assertEqual(
            generate_content.call_args.kwargs["config"].response_mime_type,
            "application/json",
        )

    def test_provider_retries_once_then_caches(self):
        class FlakyProvider(ParserProvider):
            def __init__(self):
                self.calls = 0

            def parse(self, transcript):
                self.calls += 1
                if self.calls == 1:
                    raise ParserError("temporary failure")
                return ParseResult(
                    transactions=[
                        {
                            "person": "Ramesh ji",
                            "amount": 500,
                            "type": "credit_given",
                            "note": "udhaar diya",
                        }
                    ],
                    clarification_question=None,
                )

        provider = FlakyProvider()
        with tempfile.TemporaryDirectory() as temporary:
            cache_path = Path(temporary) / "cache.sqlite3"
            with patch.dict("os.environ", {"PARSER_CACHE_PATH": str(cache_path)}):
                result = parse_transactions("Ramesh ko paanch sau udhaar diya", provider)
                self.assertEqual(provider.calls, 2)
                self.assertEqual(result[0]["person"], "Ramesh")
                cached_result = parse_transactions(
                    "Ramesh ko paanch sau udhaar diya",
                    provider,
                )
                self.assertEqual(provider.calls, 2)
                self.assertEqual(cached_result, result)

    def test_provider_failure_falls_back_after_one_retry(self):
        class FailingProvider(ParserProvider):
            def __init__(self):
                self.calls = 0

            def parse(self, transcript):
                self.calls += 1
                raise ParserError("temporary failure")

        provider = FailingProvider()
        with patch("backend.parser.time.sleep"):
            with self.assertLogs("root", level="WARNING"):
                parsed = parse_transactions(
                    "Ramesh ko paanch sau udhaar diya",
                    provider,
                    cache=False,
                )

        self.assertEqual(provider.calls, 2)
        self.assertEqual(parsed[0]["person"], "Ramesh")
        self.assertTrue(parsed.low_confidence)


if __name__ == "__main__":
    raise SystemExit(main())
