# Awaaz_khata

## Gnani API smoke test

1. Install dependencies: `python -m pip install -r requirements.txt`.
2. Copy `.env.example` to `.env` and set `GNANI_API_KEY_ID` to your Gnani API key ID.
3. Place a supported audio recording (up to 60 seconds) in `samples/`.
4. Run `python -m tests.test_gnani`. It prints the Prisma transcript and saves the Timbre response in `samples/gnani_response.mp3`.

Use `python -m tests.test_gnani --language mr-IN` for Marathi, or set `GNANI_TTS_CONTAINER=wav` in `.env` to save WAV audio. Add `--sample path/to/audio.wav` to select a particular recording. Prisma and Timbre request formats follow the official references at [docs.gnani.ai](https://docs.gnani.ai/api/STT/speech-to-text) and [docs.gnani.ai](https://docs.gnani.ai/api/TTS/tts-inference).

## Transaction parser

Install [Ollama](https://ollama.com), then download the default small model with `ollama pull qwen2.5:3b` and start Ollama. Configure `OLLAMA_HOST`, `OLLAMA_MODEL`, and `OLLAMA_TIMEOUT_SECONDS` in `.env` if needed. The parser forces a JSON schema response and validates it with Pydantic; unclear transcripts raise `ParserClarification` instead of producing ledger entries.

Run the 20-sentence evaluation with `python -m tests.test_parser`. It prints each case and the overall pass rate. The first run may take longer while the model loads.

## FastAPI ledger backend

Install dependencies with `python -m pip install -r requirements.txt`, ensure Ollama is running with the configured model, and set `GNANI_API_KEY_ID` in `.env`. Start the API with `uvicorn backend.main:app --reload`; interactive endpoint docs are available at `http://127.0.0.1:8000/docs`. SQLite data is stored in `ledger.sqlite3` by default; set `LEDGER_DATABASE_PATH` to choose another location.

`POST /voice` accepts multipart form data with an `audio` file, optional `language` (default `hi-IN`), and optional `speech_language` (default `hi-en`). It returns parsed `entries` and spoken confirmation audio as base64 with a `confirmation_id`, without saving any ledger entries. Submit that ID to `POST /confirm` as JSON with `confirmed: true` to save the entries, or `confirmed: false` to discard them. Unclear audio returns a spoken `clarification_question` and does not stage or save entries. Audio uploads are limited to 25 MB.

`GET /ledger` returns each customer balance (credit given minus payments received). `GET /customer/{name}` returns the customer's balance and transaction history. `POST /remind/{name}` returns a reminder and Timbre audio as base64; set its optional `speech_language` query parameter to choose the spoken language.

Open `http://127.0.0.1:8000/` for the mobile-friendly voice-first page. Choose Hindi, Marathi, or English and press and hold the microphone to record; the browser converts the recording to WAV before sending it. Review the transcript and entries, edit or remove any entry, then confirm to save. Timbre replies play automatically when browser audio settings allow it; playback controls are available if autoplay is blocked.

Run the API tests with `python -m unittest tests.test_api`.