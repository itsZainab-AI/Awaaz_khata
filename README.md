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