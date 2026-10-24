import base64
from contextlib import asynccontextmanager
import os
from pathlib import Path
import uuid

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from backend.database import (
    cancel_confirmation,
    confirm_transactions,
    get_customer,
    get_ledger,
    initialize_database,
    stage_confirmation,
)
from backend.gnani_client import GnaniAPIError, speak, transcribe
from backend.parser import (
    ParserClarification,
    ParserError,
    Transaction,
    parse_transactions,
)


ROOT = Path(__file__).resolve().parents[1]
MAX_AUDIO_BYTES = 25 * 1024 * 1024
load_dotenv(ROOT / ".env")
DEFAULT_DATABASE_PATH = Path(
    os.getenv("LEDGER_DATABASE_PATH", str(ROOT / "ledger.sqlite3"))
)


class ConfirmationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    confirmation_id: str = Field(min_length=1)
    confirmed: bool
    entries: list[Transaction] | None = Field(default=None, min_length=1)


def _audio_response(audio: bytes) -> dict[str, str]:
    container = os.getenv("GNANI_TTS_CONTAINER", "mp3").lower()
    content_type = "audio/wav" if container == "wav" else "audio/mpeg"
    return {
        "audio_base64": base64.b64encode(audio).decode("ascii"),
        "audio_content_type": content_type,
    }


def _speak_or_raise(text: str, language: str) -> dict[str, str]:
    try:
        audio = speak(text, language)
    except GnaniAPIError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return _audio_response(audio)


def _confirmation_text(transactions: list[dict]) -> str:
    entries = "; ".join(
        f"{item['person']}: {item['amount']:g} rupees, {item['type'].replace('_', ' ')}"
        for item in transactions
    )
    return (
        f"I heard these ledger entries: {entries}. "
        "Please confirm to save them."
    )


def create_app(database_path: Path | str = DEFAULT_DATABASE_PATH) -> FastAPI:
    resolved_database_path = Path(database_path)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        initialize_database(resolved_database_path)
        yield

    application = FastAPI(
        title="Awaaz Khata API",
        description="Voice-powered customer ledger with explicit transaction confirmation.",
        lifespan=lifespan,
    )

    @application.post("/voice")
    async def voice(
        audio: UploadFile = File(...),
        language: str = Form("hi-IN"),
        speech_language: str = Form("hi-en"),
    ) -> dict:
        audio_bytes = await audio.read(MAX_AUDIO_BYTES + 1)
        if len(audio_bytes) > MAX_AUDIO_BYTES:
            raise HTTPException(status_code=413, detail="Audio file exceeds the 25 MB limit.")
        if not audio_bytes:
            raise HTTPException(status_code=400, detail="Audio file must not be empty.")

        try:
            transcript = transcribe(audio_bytes, language_hint=language)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except GnaniAPIError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        try:
            transactions = parse_transactions(transcript)
        except ParserClarification as exc:
            speech = _speak_or_raise(exc.question, speech_language)
            return {
                "status": "clarification_required",
                "transcript": transcript,
                "clarification_question": exc.question,
                **speech,
            }
        except ParserError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        confirmation_id = str(uuid.uuid4())
        confirmation_text = _confirmation_text(transactions)
        speech = _speak_or_raise(confirmation_text, speech_language)
        stage_confirmation(
            resolved_database_path,
            confirmation_id,
            transcript,
            transactions,
        )
        return {
            "status": "confirmation_required",
            "confirmation_id": confirmation_id,
            "transcript": transcript,
            "entries": transactions,
            "confirmation_text": confirmation_text,
            **speech,
        }

    @application.post("/confirm")
    def confirm(request: ConfirmationRequest) -> dict:
        if not request.confirmed:
            if not cancel_confirmation(resolved_database_path, request.confirmation_id):
                raise HTTPException(status_code=404, detail="Pending confirmation was not found.")
            return {"status": "cancelled", "saved": False, "entries": []}

        try:
            pending = confirm_transactions(
                resolved_database_path,
                request.confirmation_id,
                edited_transactions=(
                    [entry.model_dump(mode="json") for entry in request.entries]
                    if request.entries is not None
                    else None
                ),
            )
        except (ValueError, KeyError, TypeError) as exc:
            raise HTTPException(
                status_code=500,
                detail="Pending confirmation data is invalid.",
            ) from exc
        if pending is None:
            raise HTTPException(status_code=404, detail="Pending confirmation was not found.")

        _, transactions = pending
        confirmation_text = f"Confirmed. Saved {len(transactions)} ledger entries."
        return {
            "status": "saved",
            "saved": True,
            "entries": transactions,
            "confirmation_text": confirmation_text,
        }

    @application.get("/ledger")
    def ledger() -> dict:
        return {"customers": get_ledger(resolved_database_path)}

    @application.get("/customer/{name}")
    def customer(name: str) -> dict:
        result = get_customer(resolved_database_path, name)
        if result is None:
            raise HTTPException(status_code=404, detail=f"Customer '{name}' was not found.")
        return result

    @application.post("/remind/{name}")
    def remind(name: str, speech_language: str = "hi-en") -> dict:
        result = get_customer(resolved_database_path, name)
        if result is None:
            raise HTTPException(status_code=404, detail=f"Customer '{name}' was not found.")
        balance = result["balance"]
        if balance > 0:
            reminder_text = (
                f"Hello {result['name']}, your outstanding ledger balance is "
                f"{balance:g} rupees. Please pay when convenient."
            )
        else:
            reminder_text = (
                f"Hello {result['name']}, you have no outstanding balance. Thank you."
            )
        return {
            "customer": result["name"],
            "balance": balance,
            "reminder_text": reminder_text,
            **_speak_or_raise(reminder_text, speech_language),
        }

    @application.get("/", include_in_schema=False)
    def home() -> FileResponse:
        return FileResponse(ROOT / "frontend" / "index.html")

    application.mount(
        "/frontend",
        StaticFiles(directory=ROOT / "frontend"),
        name="frontend",
    )

    return application


app = create_app()
