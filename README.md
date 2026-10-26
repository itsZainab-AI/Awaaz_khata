# Awaaz_khata

## Gnani API smoke test

1. Install dependencies: `python -m pip install -r requirements.txt`.
2. Copy `.env.example` to `.env` and set `GNANI_API_KEY_ID` to your Gnani API key ID.
3. Place a supported audio recording (up to 60 seconds) in `samples/`.
4. Run `python -m tests.test_gnani`. It prints the Prisma transcript and saves the Timbre response in `samples/gnani_response.mp3`.

Use `python -m tests.test_gnani --language mr-IN` for Marathi, or set `GNANI_TTS_CONTAINER=wav` in `.env` to save WAV audio. Add `--sample path/to/audio.wav` to select a particular recording. Prisma and Timbre request formats follow the official references at [docs.gnani.ai](https://docs.gnani.ai/api/STT/speech-to-text) and [docs.gnani.ai](https://docs.gnani.ai/api/TTS/tts-inference).

## Transaction parser

Set `GEMINI_API_KEY` in `.env`; the default model is `gemini-2.5-flash`. Override it with `PARSER_MODEL` without changing code, and optionally set `PARSER_TIMEOUT_SECONDS` and `PARSER_CACHE_PATH`. The parser uses Google's official `google-genai` SDK in JSON response mode and validates responses with Pydantic. If Gemini fails twice, a local rule parser handles common transactions and marks its list result `low_confidence`; unclear transcripts raise `ParserClarification` rather than producing ledger entries. Results are cached in SQLite by transcript SHA-256 under `.cache/` by default.

The parser also recognizes customer-only requests such as “Ramesh ke naam se khata banao” as `create_customer` intents; these create a zero-balance customer without creating a transaction. Run `python -m tests.test_parser` to report pass rates for the Gemini and fallback paths. Use `python -m tests.test_parser --path fallback` to evaluate the local rules without API calls, or `--path llm` for Gemini only. The 25 transcript cases are in `tests/parser_cases.json`.

## FastAPI ledger backend

Install dependencies with `python -m pip install -r requirements.txt`, set `GEMINI_API_KEY` and `GNANI_API_KEY_ID` in `.env`, and start the API with `uvicorn backend.main:app --reload`; interactive endpoint docs are available at `http://127.0.0.1:8000/docs`. SQLite ledger data is stored in `ledger.sqlite3` by default; set `LEDGER_DATABASE_PATH` to choose another location.

`POST /voice` accepts multipart form data with an `audio` file, optional `language` (default `hi-IN`), and optional `speech_language` (default `hi-en`). Financial entries return spoken confirmation audio as base64 with a `confirmation_id`, without saving any ledger entries. Submit that ID to `POST /confirm` as JSON with `confirmed: true` to save the entries, or `confirmed: false` to discard them. A `create_customer` intent immediately creates a zero-balance customer and returns a spoken confirmation. Unrecognized speech returns a clear message and spoken prompt without staging any entries. Audio uploads are limited to 25 MB.

`GET /ledger` returns each customer balance (credit given minus payments received), credit/paid totals, and the transaction count. `GET /customer/{name}` returns the customer's balance and transaction history. `GET /voice-example` returns Timbre audio for the ledger's sample sentence; set its optional `speech_language` query parameter to choose the spoken language. `POST /remind/{name}` returns a reminder and Timbre audio as base64; set its optional `speech_language` query parameter to choose the spoken language.

Open `http://127.0.0.1:8000/` for the mobile-friendly voice-first page. Choose Hinglish, Hindi, or Marathi and press and hold the microphone to record; the browser converts the recording to WAV before sending it. Review the transcript and entries, edit or remove any entry, then confirm to save. When there are no transactions, the page shows an animated spoken-example prompt; transcripts are romanized for Hinglish while the original transcript remains visible. Timbre replies play automatically when browser audio settings allow it; playback controls are available if autoplay is blocked.

Run the API tests with `python -m unittest tests.test_api`.