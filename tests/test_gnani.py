import argparse
import os
from pathlib import Path
import sys

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]

from backend.gnani_client import GnaniAPIError, speak, transcribe


SUPPORTED_AUDIO = {".aac", ".flac", ".m4a", ".mp3", ".ogg", ".wav"}
SAMPLE_DIR = ROOT / "samples"


def main():
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description="Run the Gnani Prisma/Timbre smoke test.")
    parser.add_argument("--sample", type=Path, help="Audio file to transcribe (default: first supported file in samples/).")
    parser.add_argument("--language", default="hi-IN", help="BCP-47 language code, e.g. hi-IN or mr-IN.")
    args = parser.parse_args()

    sample = args.sample
    if sample is None:
        candidates = sorted(
            path for path in SAMPLE_DIR.iterdir()
            if path.is_file()
            and path.suffix.lower() in SUPPORTED_AUDIO
            and not path.name.startswith("gnani_response.")
        ) if SAMPLE_DIR.exists() else []
        if not candidates:
            print("No sample audio found in samples/. Add a supported audio file (up to 60 seconds) and rerun.", file=sys.stderr)
            return 2
        sample = candidates[0]
    elif not sample.is_absolute():
        sample = ROOT / sample

    if not sample.is_file():
        print(f"Sample audio file does not exist: {sample}", file=sys.stderr)
        return 2
    if sample.suffix.lower() not in SUPPORTED_AUDIO:
        print(f"Unsupported sample format: {sample.suffix or '(no extension)'}.", file=sys.stderr)
        return 2

    container = os.getenv("GNANI_TTS_CONTAINER", "mp3").lower()
    try:
        transcript = transcribe(sample.read_bytes(), language_hint=args.language)
        print(f"Transcript: {transcript}")

        sentence = "Ramesh par ek lakh pachaas hazaar rupaye udhaar hai, aur Sita ne do crore rupaye jama kiye hain."
        audio = speak(sentence, "hi-en")
        output_path = SAMPLE_DIR / f"gnani_response.{container}"
        output_path.write_bytes(audio)
        print(f"Timbre audio saved: {output_path.relative_to(ROOT)}")
    except (GnaniAPIError, OSError, ValueError) as exc:
        print(f"Gnani test failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())