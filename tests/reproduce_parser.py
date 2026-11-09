import json
import sys
import traceback

from backend.parser import (
    ParserClarification,
    ParserError,
    _default_provider,
    _settings,
    parse_fallback,
)


TRANSCRIPTS = (
    "रमेशला 500 रुपये उधार दिले.",
    "रमेशने 300 रुपये परत दिले.",
    "सुरेशला हजार रुपये उधार दिले.",
    "रमेशकडून 200 रुपये मिळाले.",
)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

    try:
        _, model, _, _ = _settings()
        provider = _default_provider()
    except ParserError:
        print("Gemini provider initialization failed:")
        print(traceback.format_exc())
        provider = None
        model = "unavailable"

    print(f"Configured Gemini model: {model}")
    for transcript in TRANSCRIPTS:
        print(f"\nTranscript: {transcript}")
        if provider is not None:
            print("Provider: Gemini")
            try:
                parsed = provider.parse(transcript)
                if parsed.clarification_question:
                    print(f"Raw Gemini response: {provider.last_raw_response}")
                    print(f"Gemini clarification: {parsed.clarification_question}")
                print(f"Result: {json.dumps(parsed.model_dump(mode='json'), ensure_ascii=False)}")
                continue
            except Exception:
                print("Gemini exception (full traceback):")
                print(traceback.format_exc())

        print("Provider: rule-based fallback")
        try:
            print(f"Result: {json.dumps(parse_fallback(transcript), ensure_ascii=False)}")
        except ParserClarification as exc:
            print(f"Fallback clarification: {exc}")
        except Exception:
            print("Fallback exception (full traceback):")
            print(traceback.format_exc())

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
