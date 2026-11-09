import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3
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
    parse_query_intent,
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
            {
                field: transaction.get(field)
                for field in stable_fields
                if field in expected_transaction
            }
            for transaction, expected_transaction in zip(actual, expected)
        ]
        normalized_expected = [
            {
                field: transaction[field]
                for field in stable_fields
                if field in transaction
            }
            for transaction in expected
        ]
        if comparable != normalized_expected:
            raise AssertionError(f"expected {normalized_expected!r}, got {comparable!r}")
        if any(
            transaction["type"] != "create_customer" and not transaction["note"].strip()
            for transaction in actual
        ):
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
    parser_cases = [case for case in cases if not case.get("provider_only")]
    for index, case in enumerate(parser_cases, start=1):
        success, detail = _matches_case(parse, case)
        passed += success
        status = "PASS" if success else "FAIL"
        suffix = f" ({detail})" if detail else ""
        print(f"{label} {status} {index:02}: {case['transcript']}{suffix}")
    total = len(parser_cases)
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
            if case.get("provider_only"):
                continue
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

    def test_customer_case_suffixes_are_removed_from_names(self):
        from backend.parser import _normalize_person

        for name in ("रमेशला", "रमेश ने", "रमेशकडून", "रमेश को", "रमेश से"):
            with self.subTest(name=name):
                self.assertEqual(_normalize_person(name), "रमेश")

    def test_create_customer_intent_cases(self):
        cases = [
            case
            for case in self.cases
            if case.get("expected", [{}])[0].get("type") == "create_customer"
        ]
        self.assertEqual(len(cases), 5)
        for case in cases:
            with self.subTest(transcript=case["transcript"]):
                success, detail = _matches_case(parse_fallback, case)
                self.assertTrue(success, detail)

    def test_ledger_query_intents(self):
        cases = [
            (
                "Ramesh ka kitna baaki hai?",
                {"intent": "customer_balance", "person": "ramesh", "days": None},
            ),
            (
                "Aaj kitna udhaar diya?",
                {"intent": "today_credit", "person": None, "days": None},
            ),
            (
                "Kisne 30 din se nahi diya?",
                {"intent": "unpaid_since", "person": None, "days": 30},
            ),
            (
                "किसने ३० दिन से नहीं दिया?",
                {"intent": "unpaid_since", "person": None, "days": 30},
            ),
        ]
        for transcript, expected in cases:
            with self.subTest(transcript=transcript):
                parsed = parse_query_intent(transcript)
                self.assertIsNotNone(parsed)
                self.assertEqual(parsed.model_dump(), expected)

    def test_unrecognized_question_is_not_a_query(self):
        self.assertIsNone(parse_query_intent("Ramesh ko 500 udhaar diya"))
        self.assertIsNone(parse_query_intent("Who has not paid for thirty days?"))

    def test_native_language_parser_cases_cover_each_provider_only_intent(self):
        language_cases = {}
        for case in self.cases:
            if case.get("provider_only"):
                language_cases.setdefault(case["language"], set()).add(
                    case.get("query_category")
                    or case["expected"][0]["type"]
                )
        expected_categories = {
            "credit_given",
            "payment_received",
            "balance",
            "unpaid_days",
        }
        self.assertEqual(
            set(language_cases),
            {"ta-IN", "te-IN", "gu-IN", "bn-IN", "kn-IN", "ml-IN", "pa-IN", "en-IN"},
        )
        self.assertTrue(
            all(categories == expected_categories for categories in language_cases.values())
        )

    def test_non_local_query_language_uses_gemini_query_classifier(self):
        class QueryProvider:
            def __init__(self):
                self.transcript = None

            def parse_query(self, transcript):
                self.transcript = transcript
                from backend.parser import QueryIntent

                return QueryIntent(
                    intent="customer_balance",
                    person="ரமேஷ்",
                )

        provider = QueryProvider()
        with patch("backend.parser._default_provider", return_value=provider):
            from backend.parser import parse_query_intent_for_language

            parsed = parse_query_intent_for_language(
                "ரமேஷ் கணக்கில் எவ்வளவு பாக்கி இருக்கிறது?",
                "ta-IN",
            )
        self.assertEqual(provider.transcript, "ரமேஷ் கணக்கில் எவ்வளவு பாக்கி இருக்கிறது?")
        self.assertEqual(parsed.person, "ரமேஷ்")

    def test_gemini_schema_is_compatible_with_google_genai(self):
        from google.genai import types

        from backend.parser import _gemini_transaction_schema

        schema = types.Schema.model_validate(_gemini_transaction_schema())
        self.assertEqual(schema.type, types.Type.OBJECT)

    def test_gemini_failure_does_not_use_fallback_for_unsupported_language(self):
        class FailingProvider(ParserProvider):
            def parse(self, transcript):
                raise ParserError("provider unavailable")

        with patch("backend.parser.parse_fallback") as fallback:
            with self.assertRaisesRegex(ParserError, "local fallback supports only"):
                parse_transactions(
                    "தமிழில் பரிவர்த்தனை",
                    FailingProvider(),
                    cache=False,
                    language="ta-IN",
                )
        fallback.assert_not_called()

    def test_gemini_provider_requests_json_and_validates_response(self):
        provider = GeminiProvider("test-key", "test-model", 5)
        response = SimpleNamespace(
            text=(
                '{"transactions":[{"person":"Ramesh ji","normalized_person":"Ramesh","amount":500,'
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
        self.assertEqual(parsed.transactions[0].normalized_person, "Ramesh")
        self.assertEqual(
            generate_content.call_args.kwargs["config"].response_mime_type,
            "application/json",
        )
        self.assertNotIn(
            "exclusiveMinimum",
            json.dumps(generate_content.call_args.kwargs["config"].response_schema),
        )
        self.assertIn("रमेशला 500 रुपये उधार दिले", generate_content.call_args.kwargs["contents"])

    def test_gemini_clarification_keeps_raw_response_for_diagnostics(self):
        provider = GeminiProvider("test-key", "test-model", 5)
        raw_response = (
            '{"transactions":[],"clarification_question":"रमेशने किती रुपये दिले?"}'
        )
        with patch.object(
            provider._client.models,
            "generate_content",
            return_value=SimpleNamespace(text=raw_response),
        ):
            parsed = provider.parse("रमेशने 300 रुपये परत दिले.")

        self.assertEqual(parsed.clarification_question, "रमेशने किती रुपये दिले?")
        self.assertEqual(provider.last_raw_response, raw_response)

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

    def test_parser_cache_is_isolated_by_shop_id(self):
        class ShopProvider(ParserProvider):
            def __init__(self, person):
                self.person = person

            def parse(self, transcript):
                return ParseResult(
                    transactions=[{
                        "person": self.person,
                        "amount": 500,
                        "type": "credit_given",
                        "note": "udhaar diya",
                    }],
                    clarification_question=None,
                )

        with tempfile.TemporaryDirectory() as temporary:
            cache_path = Path(temporary) / "cache.sqlite3"
            with patch.dict("os.environ", {"PARSER_CACHE_PATH": str(cache_path)}):
                first_shop = parse_transactions(
                    "same voice transcript",
                    ShopProvider("Ramesh"),
                    shop_id=1,
                )
                second_shop = parse_transactions(
                    "same voice transcript",
                    ShopProvider("Sita"),
                    shop_id=2,
                )
            self.assertEqual(first_shop[0]["person"], "Ramesh")
            self.assertEqual(second_shop[0]["person"], "Sita")
            with closing(sqlite3.connect(cache_path)) as connection, connection:
                shop_ids = connection.execute(
                    "SELECT shop_id FROM parser_cache ORDER BY shop_id"
                ).fetchall()
            self.assertEqual(shop_ids, [(1,), (2,)])

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
