import os
import time

import requests
from dotenv import load_dotenv


# Endpoints, fields, model, and voice follow docs.gnani.ai API references.
PRISMA_URL = "https://api.vachana.ai/stt/v3"
TIMBRE_URL = "https://api.vachana.ai/api/v1/tts/inference"
DEFAULT_LANGUAGE = "hi-IN"
TIMBRE_MODEL = "timbre-v2.5"
TIMBRE_VOICE = "Nalini"


class GnaniAPIError(RuntimeError):
    """Raised when a Gnani request cannot be completed successfully."""


def _audio_upload(audio_bytes):
    if audio_bytes.startswith((b"RIFF", b"RF64")) and audio_bytes[8:12] == b"WAVE":
        extension, content_type = "wav", "audio/wav"
    elif audio_bytes.startswith(b"\xFF\xF1") or audio_bytes.startswith(b"\xFF\xF9"):
        extension, content_type = "aac", "audio/aac"
    elif audio_bytes.startswith(b"ID3") or (
        len(audio_bytes) > 1 and audio_bytes[0] == 0xFF and audio_bytes[1] & 0xE0 == 0xE0
    ):
        extension, content_type = "mp3", "audio/mpeg"
    elif audio_bytes.startswith(b"fLaC"):
        extension, content_type = "flac", "audio/flac"
    elif audio_bytes.startswith(b"OggS"):
        extension, content_type = "ogg", "audio/ogg"
    elif len(audio_bytes) >= 8 and audio_bytes[4:8] == b"ftyp":
        extension, content_type = "m4a", "audio/mp4"
    else:
        raise ValueError("Could not identify WAV, MP3, OGG, FLAC, AAC, or M4A audio bytes.")
    return (f"audio.{extension}", audio_bytes, content_type)


def _api_key():
    load_dotenv()
    api_key = os.getenv("GNANI_API_KEY_ID")
    if not api_key:
        raise GnaniAPIError(
            "GNANI_API_KEY_ID is missing. Add your Gnani key ID to .env."
        )
    return api_key


def _timeout():
    try:
        timeout = float(os.getenv("GNANI_REQUEST_TIMEOUT_SECONDS", "30"))
    except ValueError as exc:
        raise GnaniAPIError("GNANI_REQUEST_TIMEOUT_SECONDS must be a number.") from exc
    if timeout <= 0:
        raise GnaniAPIError("GNANI_REQUEST_TIMEOUT_SECONDS must be greater than 0.")
    return timeout


def _post(url, *, headers, timeout, retry_transient=False, **kwargs):
    attempts = 2 if retry_transient else 1
    for attempt in range(attempts):
        try:
            response = requests.post(url, headers=headers, timeout=timeout, **kwargs)
        except requests.Timeout as exc:
            raise GnaniAPIError(
                f"Gnani request timed out after {timeout:g} seconds."
            ) from exc
        except requests.RequestException as exc:
            raise GnaniAPIError(f"Could not reach Gnani: {exc}") from exc

        if retry_transient and response.status_code in (500, 503) and attempt == 0:
            time.sleep(0.5)
            continue
        if not response.ok:
            detail = response.text.strip()[:500] or "no error details returned"
            raise GnaniAPIError(
                f"Gnani returned HTTP {response.status_code}: {detail}"
            )
        return response


def transcribe(audio_bytes, language_hint=None):
    """Transcribe audio bytes with Prisma; returns the transcript string."""
    if not audio_bytes:
        raise ValueError("audio_bytes must not be empty.")
    language_code = language_hint or DEFAULT_LANGUAGE
    if not isinstance(language_code, str) or not language_code.strip():
        raise ValueError("language_hint must be a non-empty BCP-47 language code.")

    response = _post(
        PRISMA_URL,
        headers={"X-API-Key-ID": _api_key()},
        timeout=_timeout(),
        files={"audio_file": _audio_upload(audio_bytes)},
        data={"language_code": language_code, "format": "transcribe"},
    )
    try:
        result = response.json()
    except ValueError as exc:
        raise GnaniAPIError("Prisma returned a response that was not valid JSON.") from exc
    if not isinstance(result, dict):
        raise GnaniAPIError("Prisma returned an unexpected response format.")
    transcript = result.get("transcript") if result.get("success") else None
    if not isinstance(transcript, str):
        raise GnaniAPIError("Prisma response did not contain a successful transcript.")
    return transcript


def speak(text, language):
    """Synthesize speech with Timbre; returns the requested audio bytes."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("text must be a non-empty string.")
    if not isinstance(language, str) or not language.strip():
        raise ValueError("language must be a non-empty language code.")

    container = os.getenv("GNANI_TTS_CONTAINER", "mp3").lower()
    if container not in {"mp3", "wav"}:
        raise GnaniAPIError("GNANI_TTS_CONTAINER must be either 'mp3' or 'wav'.")
    audio_config = {"container": container}
    if container == "mp3":
        audio_config["bitrate"] = "128k"

    response = _post(
        TIMBRE_URL,
        headers={
            "X-API-Key-ID": _api_key(),
            "Content-Type": "application/json",
        },
        timeout=_timeout(),
        retry_transient=True,
        json={
            "text": text,
            "voice": TIMBRE_VOICE,
            "model": TIMBRE_MODEL,
            "language": language,
            "audio_config": audio_config,
        },
    )
    if not response.content:
        raise GnaniAPIError("Timbre returned an empty audio response.")
    content_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
    expected_type = "audio/mpeg" if container == "mp3" else "audio/wav"
    if content_type and content_type not in {expected_type, "application/octet-stream"}:
        raise GnaniAPIError(
            f"Timbre returned {content_type}, expected {expected_type}."
        )
    return response.content