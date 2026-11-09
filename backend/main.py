import base64
import csv
from contextlib import asynccontextmanager
from decimal import Decimal
from io import BytesIO, StringIO
import logging
import os
from pathlib import Path
import re
import sqlite3
import time
from threading import Lock
from typing import Literal
from urllib.parse import urlencode
import uuid
from xml.sax.saxutils import escape

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from PIL import Image, ImageOps

from backend.auth import (
    SESSION_COOKIE,
    SESSION_DURATION_SECONDS,
    create_session_token,
    hash_pin,
    new_process_secret,
    read_session_token,
    verify_pin,
)
from backend.database import (
    cancel_confirmation,
    confirm_transactions,
    create_customer,
    create_shop,
    delete_shop,
    get_customer,
    ensure_demo_shop,
    get_all_transactions,
    get_customer_balance,
    find_customer_match,
    get_ledger,
    get_ledger_summary,
    get_today_credit,
    get_login_lock,
    get_shop,
    get_shop_by_phone,
    get_unpaid_customers,
    initialize_database,
    lock_login,
    clear_login_failures,
    record_login_failure,
    save_transactions,
    stage_confirmation,
    update_shop_settings,
)
from backend.gnani_client import AUTO_LANGUAGE, GnaniAPIError, speak, transcribe
from backend.languages import LANGUAGES, get_template
from backend.parser import (
    ParserClarification,
    ParserError,
    QueryIntent,
    Transaction,
    parse_query_intent_for_language,
    parse_transactions,
    ScanResult,
    ScanRow,
    scan_notebook_image,
)


ROOT = Path(__file__).resolve().parents[1]
MAX_AUDIO_BYTES = 25 * 1024 * 1024
MAX_IMAGE_BYTES = 8 * 1024 * 1024
load_dotenv(ROOT / ".env")
DEFAULT_DATABASE_PATH = Path(
    os.getenv("LEDGER_DATABASE_PATH", str(ROOT / "ledger.sqlite3"))
)


class ConfirmationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    confirmation_id: str = Field(min_length=1)
    confirmed: bool
    entries: list[Transaction] | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def reject_non_transaction_intents(self):
        if self.entries and any(entry.type == "create_customer" for entry in self.entries):
            raise ValueError("Customer creation cannot be saved as a transaction.")
        return self


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shop_name: str = Field(min_length=2, max_length=80)
    owner_name: str = Field(min_length=2, max_length=80)
    phone: str = Field(min_length=10, max_length=16)
    pin: str = Field(min_length=4, max_length=6, pattern=r"^[0-9]{4,6}$")
    language: str = "hi-en"
    upi_id: str = Field(default="", max_length=120)

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, phone: str) -> str:
        normalized = phone.replace(" ", "").replace("-", "")
        if not normalized.removeprefix("+").isdigit() or not 10 <= len(normalized.removeprefix("+")) <= 15:
            raise ValueError("Enter a valid phone number with country code if needed.")
        return normalized

    @field_validator("language")
    @classmethod
    def validate_language(cls, language: str) -> str:
        if language not in LANGUAGES.keys():
            raise ValueError("Choose a supported language.")
        return language


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phone: str = Field(min_length=10, max_length=16)
    pin: str = Field(min_length=4, max_length=6, pattern=r"^[0-9]{4,6}$")


class SettingsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shop_name: str = Field(min_length=2, max_length=80)
    language: str
    upi_id: str = Field(default="", max_length=120)

    @field_validator("language")
    @classmethod
    def validate_language(cls, language: str) -> str:
        if language not in LANGUAGES.keys():
            raise ValueError("Choose a supported language.")
        return language


def _audio_response(audio: bytes) -> dict[str, str]:
    container = os.getenv("GNANI_TTS_CONTAINER", "mp3").lower()
    content_type = "audio/wav" if container == "wav" else "audio/mpeg"
    return {
        "audio_base64": base64.b64encode(audio).decode("ascii"),
        "audio_content_type": content_type,
    }


def _speak_or_raise(text: str, language: str) -> dict[str, str]:
    language_config = LANGUAGES.get(language)
    if language_config is None:
        raise HTTPException(status_code=400, detail="Choose a supported language.")
    if not language_config["tts_available"]:
        return {}
    try:
        audio = speak(text, language)
    except GnaniAPIError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return _audio_response(audio)


def _language_for_stt_code(stt_code: str | None) -> tuple[str, dict] | None:
    if not stt_code:
        return None
    for code, language in LANGUAGES.items():
        if language["stt_code"] == stt_code and language["tts_code"] == stt_code:
            return code, language
    for code, language in LANGUAGES.items():
        if language["stt_code"] == stt_code:
            return code, language
    return None


def _confirmation_text(transactions: list[dict]) -> str:
    entries = "; ".join(
        f"{item['person']}: {item['amount']:g} rupees, {item['type'].replace('_', ' ')}"
        for item in transactions
    )
    return (
        f"I heard these ledger entries: {entries}. "
        "Please confirm to save them."
    )


def _ledger_query_answer(
    database_path: Path,
    shop_id: int,
    query: QueryIntent,
    language: str,
) -> str:
    if query.intent == "customer_balance":
        customer = get_customer_balance(database_path, shop_id, query.person or "")
        if customer is None:
            return get_template(language, "customer_not_found", name=query.person or "")
        balance = float(customer["balance"])
        amount = f"₹{abs(balance):,.2f}".replace(".00", "")
        if balance > 0:
            return get_template(language, "owes_you", name=customer["name"], amount=amount)
        if balance < 0:
            return get_template(language, "you_owe", name=customer["name"], amount=amount)
        return get_template(language, "settled", name=customer["name"])

    if query.intent == "today_credit":
        amount = f"₹{get_today_credit(database_path, shop_id):,.2f}".replace(".00", "")
        return get_template(language, "today_credit", amount=amount)

    days = query.days or 30
    customers = get_unpaid_customers(database_path, shop_id, days)
    if not customers:
        return get_template(language, "no_unpaid", days=str(days))
    names = ", ".join(
        f"{customer['name']} ₹{customer['balance']:,.2f}".replace(".00", "")
        for customer in customers
    )
    return get_template(language, "unpaid_list", days=str(days), names=names)


def _csv_export(rows: list[list[object]]) -> bytes:
    output = StringIO(newline="")
    writer = csv.writer(output)
    writer.writerows(rows)
    return ("\ufeff" + output.getvalue()).encode("utf-8")


_PDF_SCRIPT_FONTS = {
    "devanagari": "AwaazDevanagari",
    "bengali": "AwaazBengali",
    "gurmukhi": "AwaazGurmukhi",
    "gujarati": "AwaazGujarati",
    "tamil": "AwaazTamil",
    "telugu": "AwaazTelugu",
    "kannada": "AwaazKannada",
    "malayalam": "AwaazMalayalam",
}
_PDF_FONT_LOCK = Lock()
_PDF_SCRIPT_RANGES = (
    (0x0900, 0x097F, "devanagari"),
    (0x0980, 0x09FF, "bengali"),
    (0x0A00, 0x0A7F, "gurmukhi"),
    (0x0A80, 0x0AFF, "gujarati"),
    (0x0B80, 0x0BFF, "tamil"),
    (0x0C00, 0x0C7F, "telugu"),
    (0x0C80, 0x0CFF, "kannada"),
    (0x0D00, 0x0D7F, "malayalam"),
)


def _pdf_script(character: str) -> str | None:
    codepoint = ord(character)
    for start, end, script in _PDF_SCRIPT_RANGES:
        if start <= codepoint <= end:
            return script
    if character.isascii() and character.isalnum():
        return "devanagari"
    return None


def _pdf_runs(text: str) -> list[tuple[str, str]]:
    runs: list[tuple[str, str]] = []
    current_script = "devanagari"
    current_text = ""
    for character in text:
        script = _pdf_script(character) or current_script
        if script != current_script and current_text:
            runs.append((current_script, current_text))
            current_text = ""
        current_script = script
        current_text += character
    if current_text:
        runs.append((current_script, current_text))
    return runs


def _pdf_markup(text: str) -> str:
    return "".join(
        f'<font name="{_PDF_SCRIPT_FONTS[script]}">{escape(run)}</font>'
        for script, run in _pdf_runs(text)
    )


def _pdf_export(title: str, rows: list[list[object]]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle

    fonts_directory = ROOT / "fonts"
    font_files = {
        "devanagari": "NotoSansDevanagari.ttf",
        "bengali": "NotoSansBengali.ttf",
        "gurmukhi": "NotoSansGurmukhi.ttf",
        "gujarati": "NotoSansGujarati.ttf",
        "tamil": "NotoSansTamil.ttf",
        "telugu": "NotoSansTelugu.ttf",
        "kannada": "NotoSansKannada.ttf",
        "malayalam": "NotoSansMalayalam.ttf",
    }
    with _PDF_FONT_LOCK:
        registered_fonts = set(pdfmetrics.getRegisteredFontNames())
        for script, filename in font_files.items():
            font_name = _PDF_SCRIPT_FONTS[script]
            if font_name not in registered_fonts:
                font_path = fonts_directory / filename
                if not font_path.is_file():
                    raise HTTPException(
                        status_code=500,
                        detail=f"PDF export is missing the bundled Noto Sans font: {filename}.",
                    )
                pdfmetrics.registerFont(TTFont(font_name, str(font_path), shapable=True))
                registered_fonts.add(font_name)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "AwaazTitle",
        parent=styles["Title"],
        fontName=_PDF_SCRIPT_FONTS["devanagari"],
        alignment=TA_LEFT,
        textColor=colors.HexColor("#592a10"),
        shaping=1,
    )
    cell_style = ParagraphStyle(
        "AwaazCell",
        parent=styles["BodyText"],
        fontName=_PDF_SCRIPT_FONTS["devanagari"],
        fontSize=7.5,
        leading=10,
        wordWrap="CJK",
        shaping=1,
    )
    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=32,
        rightMargin=32,
        topMargin=36,
        bottomMargin=36,
        title=title,
    )
    content = [Paragraph(_pdf_markup(title), title_style), Spacer(1, 14)]
    table_data = [
        [Paragraph(_pdf_markup(str(value)), cell_style) for value in row]
        for row in rows
    ]
    table = LongTable(table_data, repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f2a541")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#201514")),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#dbc9b4")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    content.append(table)
    document.build(content)
    return output.getvalue()


def _export_response(
    rows: list[list[object]],
    filename: str,
    title: str,
    export_format: Literal["csv", "pdf"],
) -> Response:
    safe_filename = re.sub(r"[^A-Za-z0-9_-]+", "-", filename).strip("-") or "khata"
    if export_format == "csv":
        return Response(
            content=_csv_export(rows),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{safe_filename}.csv"'},
        )
    return Response(
        content=_pdf_export(title, rows),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{safe_filename}.pdf"'},
    )


def create_app(database_path: Path | str = DEFAULT_DATABASE_PATH) -> FastAPI:
    resolved_database_path = Path(database_path)
    configured_jwt_secret = os.getenv("JWT_SECRET", "").strip()
    if configured_jwt_secret and len(configured_jwt_secret) < 32:
        raise ValueError("JWT_SECRET must contain at least 32 characters.")
    jwt_secret = configured_jwt_secret.encode("utf-8") or new_process_secret()
    demo_pin_hash = hash_pin(uuid.uuid4().hex)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        legacy_phone = os.getenv("LEGACY_SHOP_PHONE", "").strip()
        legacy_pin = os.getenv("LEGACY_SHOP_PIN", "").strip()
        legacy_pin_hash = (
            hash_pin(legacy_pin)
            if legacy_phone and re.fullmatch(r"[0-9]{4,6}", legacy_pin)
            else ""
        )
        initialize_database(
            resolved_database_path,
            legacy_phone=legacy_phone if legacy_pin_hash else "",
            legacy_pin_hash=legacy_pin_hash,
        )
        yield

    application = FastAPI(
        title="Awaaz Khata API",
        description="Voice-powered customer ledger with explicit transaction confirmation.",
        lifespan=lifespan,
    )

    def current_shop_id(request: Request) -> int:
        token = request.cookies.get(SESSION_COOKIE, "")
        shop_id = read_session_token(token, jwt_secret)
        if shop_id is None or get_shop(resolved_database_path, shop_id) is None:
            raise HTTPException(status_code=401, detail="Please log in to continue.")
        return shop_id

    def set_session_cookie(response: Response, shop_id: int) -> None:
        response.set_cookie(
            SESSION_COOKIE,
            create_session_token(shop_id, jwt_secret),
            max_age=SESSION_DURATION_SECONDS,
            httponly=True,
            secure=os.getenv("COOKIE_SECURE", "false").lower() == "true",
            samesite="strict",
            path="/",
        )

    @application.post("/api/register", status_code=201)
    def register(request: RegisterRequest, response: Response) -> dict:
        try:
            shop_id = create_shop(
                resolved_database_path,
                shop_name=request.shop_name.strip(),
                owner_name=request.owner_name.strip(),
                phone=request.phone,
                pin_hash=hash_pin(request.pin),
                language=request.language,
                upi_id=request.upi_id.strip(),
            )
        except sqlite3.IntegrityError as exc:
            raise HTTPException(
                status_code=409,
                detail="An account already uses this phone number. Please log in.",
            ) from exc
        set_session_cookie(response, shop_id)
        return {"shop": get_shop(resolved_database_path, shop_id)}

    @application.post("/api/login")
    def login(request: LoginRequest, response: Response) -> dict:
        phone = request.phone.replace(" ", "").replace("-", "")
        failures, locked_until = get_login_lock(resolved_database_path, phone)
        now = int(time.time())
        if locked_until > now:
            raise HTTPException(
                status_code=429,
                detail=f"Too many incorrect attempts. Try again in {locked_until - now} seconds.",
                headers={"Retry-After": str(locked_until - now)},
            )

        shop = get_shop_by_phone(resolved_database_path, phone)
        if shop is None or not verify_pin(request.pin, shop["pin_hash"]):
            failures = record_login_failure(
                resolved_database_path, phone, shop["id"] if shop else None
            )
            if failures >= 5:
                locked_until = now + 15 * 60
                lock_login(resolved_database_path, phone, locked_until)
                raise HTTPException(
                    status_code=429,
                    detail="Too many incorrect attempts. Try again in 15 minutes.",
                    headers={"Retry-After": "900"},
                )
            raise HTTPException(status_code=401, detail="Phone number or PIN is incorrect.")

        clear_login_failures(resolved_database_path, phone)
        set_session_cookie(response, shop["id"])
        return {"shop": get_shop(resolved_database_path, shop["id"])}

    @application.post("/api/demo-login")
    def demo_login(response: Response) -> dict:
        shop_id = ensure_demo_shop(resolved_database_path, demo_pin_hash)
        set_session_cookie(response, shop_id)
        return {"shop": get_shop(resolved_database_path, shop_id)}

    @application.post("/api/logout")
    def logout(response: Response, _: int = Depends(current_shop_id)) -> dict:
        response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, samesite="strict")
        return {"status": "logged_out"}

    @application.get("/api/languages")
    def languages() -> list[dict[str, str | bool]]:
        return [
            {
                "code": code,
                "label": language["label"],
                "native_label": language["native_label"],
                "stt_code": language["stt_code"],
                "tts_code": language["tts_code"],
                "transliterate_transcript": language["transliterate_transcript"],
                "copy_language": language["copy_language"],
            }
            for code, language in LANGUAGES.items()
        ]

    @application.get("/api/me")
    def me(shop_id: int = Depends(current_shop_id)) -> dict:
        return {"shop": get_shop(resolved_database_path, shop_id)}

    @application.patch("/api/settings")
    def update_settings(
        request: SettingsRequest,
        shop_id: int = Depends(current_shop_id),
    ) -> dict:
        shop = get_shop(resolved_database_path, shop_id)
        if shop and shop["is_demo"]:
            raise HTTPException(
                status_code=403,
                detail="Demo shop settings are read-only. Create an account to personalize your khata.",
            )
        update_shop_settings(
            resolved_database_path,
            shop_id,
            shop_name=request.shop_name.strip(),
            language=request.language,
            upi_id=request.upi_id.strip(),
        )
        return {"shop": get_shop(resolved_database_path, shop_id)}

    @application.delete("/api/account", status_code=204)
    def delete_account(response: Response, shop_id: int = Depends(current_shop_id)):
        shop = get_shop(resolved_database_path, shop_id)
        if shop and shop["is_demo"]:
            raise HTTPException(status_code=403, detail="The shared demo shop cannot be deleted.")
        delete_shop(resolved_database_path, shop_id)
        response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, samesite="strict")
        return Response(status_code=204)

    @application.post("/voice")
    async def voice(
        audio: UploadFile = File(...),
        language: str = Form("hi-IN"),
        speech_language: str = Form("hi-en"),
        shop_id: int = Depends(current_shop_id),
    ) -> dict:
        audio_bytes = await audio.read(MAX_AUDIO_BYTES + 1)
        if len(audio_bytes) > MAX_AUDIO_BYTES:
            raise HTTPException(status_code=413, detail="Audio file exceeds the 25 MB limit.")
        if not audio_bytes:
            raise HTTPException(status_code=400, detail="Audio file must not be empty.")
        is_auto = language == "auto"
        language_config = None if is_auto else next(
            (
                config
                for code, config in LANGUAGES.items()
                if code == language or config["stt_code"] == language
            ),
            None,
        )
        if not is_auto and language_config is None:
            raise HTTPException(status_code=400, detail="Choose a supported language.")

        try:
            transcription = transcribe(
                audio_bytes,
                language_hint=AUTO_LANGUAGE if is_auto else language_config["stt_code"],
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except GnaniAPIError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        transcript = str(transcription)
        detected_language_code = getattr(transcription, "detected_language_code", None)
        detected_language = _language_for_stt_code(detected_language_code)
        detected_language_response = (
            {
                "code": detected_language[0],
                "label": detected_language[1]["label"],
                "native_label": detected_language[1]["native_label"],
            }
            if detected_language
            else None
        )
        if is_auto:
            spoken_language = (
                detected_language[0]
                if detected_language
                else (get_shop(resolved_database_path, shop_id) or {}).get(
                    "language", "hi-en"
                )
            )
            parser_language = detected_language[0] if detected_language else "auto"
        else:
            spoken_language = speech_language
            parser_language = next(
                (
                    code
                    for code, config in LANGUAGES.items()
                    if config["tts_code"] == speech_language
                ),
                language_config["label"],
            )

        if not transcript.strip():
            message = get_template(spoken_language, "samajh_nahi_aaya")
            return {
                "status": "unrecognized",
                "transcript": transcript,
                "detected_language": detected_language_response,
                "message": message,
                **_speak_or_raise(message, spoken_language),
            }

        try:
            query_intent = parse_query_intent_for_language(transcript, parser_language)
        except ParserError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        if query_intent is not None:
            shop = get_shop(resolved_database_path, shop_id)
            answer = _ledger_query_answer(
                resolved_database_path,
                shop_id,
                query_intent,
                spoken_language,
            )
            return {
                "status": "query_answer",
                "transcript": transcript,
                "detected_language": detected_language_response,
                "answer": answer,
                **_speak_or_raise(answer, spoken_language),
            }

        try:
            transactions = parse_transactions(
                transcript,
                shop_id=shop_id,
                language=parser_language,
            )
        except ParserClarification as exc:
            message = (
                exc.question
                if parser_language not in {"hi-en", "hi-IN", "mr-IN"}
                else get_template(spoken_language, "samajh_nahi_aaya")
            )
            return {
                "status": "unrecognized",
                "transcript": transcript,
                "detected_language": detected_language_response,
                "message": message,
                **_speak_or_raise(message, spoken_language),
            }
        except ParserError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        if len(transactions) == 1 and transactions[0]["type"] == "create_customer":
            customer_name = transactions[0]["person"]
            confirmation_text = f"{customer_name} ka khata ban gaya"
            speech = _speak_or_raise(confirmation_text, spoken_language)
            shop = get_shop(resolved_database_path, shop_id)
            customer = create_customer(
                resolved_database_path,
                shop_id,
                customer_name,
                preferred_language=shop["language"] if shop else "hi-en",
            )
            return {
                "status": "customer_created",
                "transcript": transcript,
                "detected_language": detected_language_response,
                "customer": customer,
                "confirmation_text": confirmation_text,
                **speech,
            }

        review_entries = []
        for transaction in transactions:
            match_name = transaction.get("normalized_person") or transaction["person"]
            customer_match = find_customer_match(
                resolved_database_path,
                shop_id,
                match_name,
            )
            heard_name = transaction["person"].strip().casefold()
            matched_name = customer_match["name"].strip().casefold() if customer_match else ""
            if customer_match and (
                not customer_match["exact"] or heard_name != matched_name
            ):
                transaction = {
                    **transaction,
                    "original_person": transaction["person"],
                    "person": customer_match["name"],
                    "match_suggestion": customer_match["name"],
                }
            review_entries.append(transaction)
        transactions = review_entries

        confirmation_id = str(uuid.uuid4())
        confirmation_text = _confirmation_text(transactions)
        speech = _speak_or_raise(confirmation_text, spoken_language)
        stage_confirmation(
            resolved_database_path,
            shop_id,
            confirmation_id,
            transcript,
            transactions,
        )
        return {
            "status": "confirmation_required",
            "confirmation_id": confirmation_id,
            "transcript": transcript,
            "detected_language": detected_language_response,
            "entries": transactions,
            "confirmation_text": confirmation_text,
            **speech,
        }

    @application.post("/scan-notebook")
    async def scan_notebook(
        image: UploadFile = File(...),
        shop_id: int = Depends(current_shop_id),
    ) -> dict:
        raw_bytes = await image.read()
        if len(raw_bytes) > MAX_IMAGE_BYTES:
            raise HTTPException(
                status_code=400,
                detail="Image size exceeds 8 MB limit.",
            )
        if not raw_bytes:
            raise HTTPException(
                status_code=400,
                detail="Uploaded image is empty.",
            )

        try:
            img = Image.open(BytesIO(raw_bytes))
            img_format = (img.format or "").upper()
            if img_format not in ("JPEG", "JPG", "PNG", "WEBP", "HEIC", "HEIF"):
                raise HTTPException(
                    status_code=400,
                    detail="Unsupported file format. Please upload a JPG, PNG, WEBP, or HEIC image.",
                )
            img.verify()
            img = Image.open(BytesIO(raw_bytes))
        except HTTPException:
            raise
        except Exception as exc:
            logging.exception("Could not decode uploaded notebook image")
            raise HTTPException(
                status_code=400,
                detail="Uploaded file is not a valid image.",
            ) from exc

        try:
            img = ImageOps.exif_transpose(img)
        except Exception as exc:
            logging.exception("Could not orient uploaded notebook image")
            raise HTTPException(
                status_code=400,
                detail=f"Could not process uploaded image: {exc}",
            ) from exc

        long_side = max(img.width, img.height)
        if long_side > 1280:
            img.thumbnail((1280, 1280), Image.Resampling.LANCZOS)

        buffer = BytesIO()
        img = img.convert("RGB")
        img.save(buffer, format="JPEG", quality=85)
        mime_type = "image/jpeg"

        processed_bytes = buffer.getvalue()
        if not processed_bytes:
            raise HTTPException(status_code=400, detail="Could not process uploaded image.")

        try:
            scan_result = scan_notebook_image(processed_bytes, mime_type=mime_type)
        except Exception as exc:
            logging.exception("Notebook scan failed")
            raise HTTPException(
                status_code=502,
                detail=str(exc),
            ) from exc

        logging.info("Gemini notebook scan response: %s", scan_result.raw_response)

        if not scan_result.rows:
            return {
                "status": "no_entries",
                "drafts": [],
                "entries": [],
            }

        drafts = []
        for row in scan_result.rows:
            customer_match = (
                find_customer_match(resolved_database_path, shop_id, row.person)
                if row.person
                else None
            )
            matched_customer_id = customer_match["id"] if customer_match else None
            is_new_customer = customer_match is None
            matched_name = customer_match["name"] if customer_match else row.person

            drafts.append({
                "person": matched_name,
                "original_person": row.person,
                "amount": row.amount,
                "type": row.type,
                "note": row.note,
                "date": row.date,
                "confidence": row.confidence,
                "matched_customer_id": matched_customer_id,
                "is_new_customer": is_new_customer,
                "match_suggestion": (
                    matched_name
                    if not is_new_customer and matched_name != row.person
                    else None
                ),
            })

        return {
            "status": "success",
            "drafts": drafts,
            "entries": drafts,
        }

    @application.post("/confirm")
    def confirm(request: ConfirmationRequest, shop_id: int = Depends(current_shop_id)) -> dict:
        if not request.confirmed:
            if not cancel_confirmation(resolved_database_path, shop_id, request.confirmation_id):
                if not request.confirmation_id.startswith("scan-"):
                    raise HTTPException(status_code=404, detail="Pending confirmation was not found.")
            return {"status": "cancelled", "saved": False, "entries": []}

        try:
            pending = confirm_transactions(
                resolved_database_path,
                shop_id,
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
            if request.entries:
                saved = save_transactions(
                    resolved_database_path,
                    shop_id,
                    [entry.model_dump(mode="json") for entry in request.entries],
                )
                confirmation_text = f"Confirmed. Saved {len(saved)} ledger entries."
                return {
                    "status": "saved",
                    "saved": True,
                    "entries": saved,
                    "confirmation_text": confirmation_text,
                }
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
    def ledger(shop_id: int = Depends(current_shop_id)) -> dict:
        return {
            "customers": get_ledger(resolved_database_path, shop_id),
            "summary": get_ledger_summary(resolved_database_path, shop_id),
        }

    @application.get("/voice-example")
    def voice_example(
        speech_language: str = "hi-en",
        _: int = Depends(current_shop_id),
    ) -> dict:
        return _speak_or_raise("Ramesh ko 500 udhaar diya", speech_language)

    @application.get("/customer/{name}")
    def customer(name: str, shop_id: int = Depends(current_shop_id)) -> dict:
        result = get_customer(resolved_database_path, shop_id, name)
        if result is None:
            raise HTTPException(status_code=404, detail=f"Customer '{name}' was not found.")
        return result

    @application.post("/remind/{name}")
    def remind(
        name: str,
        speech_language: str | None = None,
        shop_id: int = Depends(current_shop_id),
    ) -> dict:
        result = get_customer(resolved_database_path, shop_id, name)
        if result is None:
            raise HTTPException(status_code=404, detail=f"Customer '{name}' was not found.")
        balance = result["balance"]
        language = result["preferred_language"]
        if balance > 0:
            formatted_balance = f"{balance:,.2f}".rstrip("0").rstrip(".")
            reminder_text = get_template(
                language,
                "reminder_due",
                name=result["name"],
                amount=f"₹{formatted_balance}",
            )
        else:
            reminder_text = get_template(language, "reminder_clear", name=result["name"])
        digits = re.sub(r"\D", "", result["phone"] or "")
        if len(digits) == 10:
            digits = f"91{digits}"
        whatsapp_path = f"https://wa.me/{digits}" if len(digits) >= 11 else "https://wa.me/"
        whatsapp_url = f"{whatsapp_path}?{urlencode({'text': reminder_text})}"
        shop = get_shop(resolved_database_path, shop_id)
        upi_link = None
        if balance > 0 and shop and shop["upi_id"]:
            exact_amount = format(
                Decimal(str(balance)).quantize(Decimal("0.01")),
                "f",
            )
            upi_link = "upi://pay?" + urlencode({
                "pa": shop["upi_id"],
                "pn": shop["shop_name"],
                "am": exact_amount,
                "cu": "INR",
                "tn": f"Khata payment for {result['name']}",
            })
        spoken_language = speech_language or language
        return {
            "customer": result["name"],
            "balance": balance,
            "language": language,
            "reminder_text": reminder_text,
            "whatsapp_url": whatsapp_url,
            "upi_link": upi_link,
            **_speak_or_raise(reminder_text, spoken_language),
        }

    @application.get("/export/customer/{name}")
    def export_customer(
        name: str,
        format: Literal["csv", "pdf"] = "csv",
        shop_id: int = Depends(current_shop_id),
    ) -> Response:
        customer = get_customer(resolved_database_path, shop_id, name)
        if customer is None:
            raise HTTPException(status_code=404, detail=f"Customer '{name}' was not found.")
        rows: list[list[object]] = [
            ["Customer", "Type", "Amount (INR)", "Note", "Date"],
            *[
                [
                    customer["name"],
                    transaction["type"],
                    transaction["amount"],
                    transaction["note"],
                    transaction["created_at"],
                ]
                for transaction in customer["transactions"]
            ],
        ]
        return _export_response(
            rows,
            f"{customer['name']}-khata",
            f"{customer['name']} khata · Balance ₹{customer['balance']:g}",
            format,
        )

    @application.get("/export/ledger")
    def export_ledger(
        format: Literal["csv", "pdf"] = "csv",
        shop_id: int = Depends(current_shop_id),
    ) -> Response:
        rows: list[list[object]] = [
            ["Customer", "Type", "Amount (INR)", "Note", "Date"],
            *[
                [
                    transaction["customer"],
                    transaction["type"],
                    transaction["amount"],
                    transaction["note"],
                    transaction["created_at"],
                ]
                for transaction in get_all_transactions(resolved_database_path, shop_id)
            ],
        ]
        return _export_response(rows, "awaaz-khata-ledger", "Awaaz Khata · Full ledger", format)
    @application.get("/", include_in_schema=False)
    def home() -> FileResponse:
        return FileResponse(ROOT / "frontend" / "landing.html")

    @application.get("/dashboard", include_in_schema=False)
    def dashboard() -> FileResponse:
        return FileResponse(ROOT / "frontend" / "index.html")

    @application.get("/settings", include_in_schema=False)
    def settings_page() -> FileResponse:
        return FileResponse(ROOT / "frontend" / "settings.html")

    @application.get("/service-worker.js", include_in_schema=True)
    def service_worker() -> FileResponse:
        return FileResponse(
            ROOT / "frontend" / "service-worker.js",
            media_type="text/javascript",
            headers={"Service-Worker-Allowed": "/"},
        )

    @application.get("/offline.html", include_in_schema=False)
    def offline_page() -> FileResponse:
        return FileResponse(ROOT / "frontend" / "offline.html")

    @application.get("/login", include_in_schema=False)
    @application.get("/register", include_in_schema=False)
    def authentication_page() -> FileResponse:
        return FileResponse(ROOT / "frontend" / "auth.html")

    application.mount(
        "/frontend",
        StaticFiles(directory=ROOT / "frontend"),
        name="frontend",
    )

    return application


app = create_app()
