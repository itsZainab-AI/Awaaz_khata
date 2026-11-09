import hashlib
import json
import logging
import math
import os
import re
import sqlite3
import time
from abc import ABC, abstractmethod
from collections.abc import Iterable
from contextlib import closing
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from unidecode import unidecode


ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


class ParserError(RuntimeError):
    """Raised when the configured parser cannot return valid output."""


class ParserClarification(RuntimeError):
    """Raised when a transcript needs clarification before ledger entry."""

    def __init__(self, question: str):
        self.question = question
        super().__init__(question)


class Transaction(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    person: str = Field(min_length=1)
    normalized_person: str | None = Field(default=None, min_length=1)
    amount: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    type: Literal["credit_given", "payment_received", "create_customer"]
    note: str = Field(default="", max_length=80)

    @model_validator(mode="after")
    def normalize_fields(self):
        self.person = _normalize_person(self.person)
        if self.normalized_person is not None:
            self.normalized_person = _normalize_person(self.normalized_person)
        self.note = _normalize_note(self.note, self.person, self.amount)
        if not self.person:
            raise ValueError("person must contain a name")
        if self.type == "create_customer" and self.amount is not None:
            raise ValueError("customer creation must not include an amount")
        if self.type != "create_customer" and self.amount is None:
            raise ValueError("transactions must include an amount")
        if self.type != "create_customer" and not self.note:
            raise ValueError("transactions must include a note")
        return self


class QueryIntent(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    intent: Literal["customer_balance", "today_credit", "unpaid_since"]
    person: str | None = None
    days: int | None = Field(default=None, ge=1, le=365)

    @model_validator(mode="after")
    def validate_query(self):
        if self.intent == "customer_balance" and not self.person:
            raise ValueError("customer balance queries require a customer name")
        if self.intent == "unpaid_since" and self.days is None:
            raise ValueError("unpaid queries require a number of days")
        return self


class QueryClassification(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    intent: Literal["customer_balance", "today_credit", "unpaid_since", "not_query"]
    person: str | None = None
    days: int | None = Field(default=None, ge=1, le=365)


class ScanRow(BaseModel):
    # Use extra="ignore" and no strict=True so Pydantic does NOT emit
    # "additionalProperties": false in the JSON schema — Gemini rejects that field.
    model_config = ConfigDict(extra="ignore")

    person: str = ""
    amount: float
    type: Literal["credit_given", "payment_received"] = "credit_given"
    note: str = ""
    date: str | None = None
    confidence: Literal["low", "medium", "high"] = "high"

    @model_validator(mode="after")
    def validate_row(self):
        self.person = _normalize_person(self.person)
        if not math.isfinite(self.amount) or self.amount <= 0:
            raise ValueError("amount must be greater than zero")
        if not self.note:
            self.note = "Notebook entry"
        return self


class ScanResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    rows: list[ScanRow]
    raw_response: str | None = Field(default=None, exclude=True)


class ParseResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    transactions: list[Transaction]
    clarification_question: str | None

    @model_validator(mode="after")
    def validate_result(self):
        has_question = bool(self.clarification_question and self.clarification_question.strip())
        if has_question == bool(self.transactions):
            raise ValueError("Return transactions or a clarification question, not both")
        customer_intents = [
            transaction
            for transaction in self.transactions
            if transaction.type == "create_customer"
        ]
        if customer_intents and (
            len(self.transactions) != 1 or len(customer_intents) != 1
        ):
            raise ValueError("Customer creation must be the only parser intent")
        return self


class ParsedTransactions(list[dict]):
    """JSON-list-compatible return value carrying fallback provenance."""

    def __init__(
        self,
        transactions: Iterable[dict] = (),
        *,
        low_confidence: bool = False,
    ) -> None:
        super().__init__(transactions)
        self.low_confidence: bool = low_confidence


class ParserProvider(ABC):
    """Provider contract for structured transaction parsing."""

    @abstractmethod
    def parse(self, transcript: str) -> ParseResult:
        """Return validated transaction data or a clarification question."""


class GeminiProvider(ParserProvider):
    def __init__(self, api_key: str, model: str, timeout_seconds: float):
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise ParserError(
                "Gemini support requires google-genai. Install the project requirements."
            ) from exc

        self._types = types
        self._client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=int(timeout_seconds * 1000)),
        )
        self._model = model
        self.last_raw_response: str | None = None

    def parse(self, transcript: str) -> ParseResult:
        prompt = (
            "Parse shopkeeper ledger speech in Hinglish, Hindi, Marathi, Tamil, "
            "Telugu, Gujarati, Bengali, Kannada, Malayalam, Punjabi or English, "
            "including natural code-switching. "
            "Return every distinct completed transaction in speech order. "
            "Customer names may have grammatical case suffixes attached; these "
            "suffixes are not part of the name and must be stripped. Marathi "
            "examples include ला, ने, कडून, चा, ची; Hindi includes को, ने, से; "
            "Tamil includes க்கு/உக்கு; Telugu includes కు/కి/నుంచి; likewise "
            "strip equivalent case endings in Gujarati, Bengali, Kannada, "
            "Malayalam and Punjabi. For example, रमेशला means person रमेश. "
            "credit_given means the shopkeeper gave goods or money on credit "
            "and the named person owes the shopkeeper. payment_received means "
            "the person paid or returned money to the shopkeeper. Convert spoken "
            "requests to create a customer khata, such as 'Ramesh ke naam se "
            "khata banao', to type create_customer with person, null amount, "
            "and an empty note. This is not a financial transaction. "
            "amounts to numeric rupees (paanch sau=500, dedh hazaar=1500, "
            "sava hazaar=1250, ek lakh=100000, ek crore=10000000). Remove "
            "honorifics such as ji/jee from names. Preserve each customer name in "
            "the original script in person and include a Romanized normalized_person "
            "for matching. Give each financial transaction "
            "a short contextual note. Never infer a missing person, amount, or direction. "
            "Few-shot examples (each is one completed transaction): "
            "Hinglish: 'Ramesh ko 500 udhaar diya' -> person Ramesh, amount 500, "
            "credit_given. Hindi: 'रमेश को पाँच सौ उधार दिए' -> person रमेश, "
            "amount 500, credit_given. Marathi: 'रमेशला 500 रुपये उधार दिले' "
            "-> person रमेश, amount 500, credit_given; 'रमेशने 300 रुपये परत "
            "दिले' -> person रमेश, amount 300, payment_received. Tamil: "
            "'ரமேஷுக்கு 500 ரூபாய் கடனாக கொடுத்தேன்' -> person ரமேஷ், "
            "credit_given. Telugu: 'రమేష్‌కు 500 రూపాయలు అప్పుగా ఇచ్చాను' "
            "-> person రమేష్, credit_given. Gujarati: 'રમેશને 500 રૂપિયા "
            "ઉધાર આપ્યા' -> person રમેશ, credit_given. Bengali: "
            "'রাকেশকে 500 টাকা ধার দিলাম' -> person রাকেশ, credit_given. "
            "Kannada: 'ರಮೇಶ್‌ಗೆ 500 ರೂಪಾಯಿ ಸಾಲವಾಗಿ ಕೊಟ್ಟೆ' -> person ರಮೇಶ್, "
            "credit_given. Malayalam: 'രമേശിന് 500 രൂപ കടമായി കൊടുത്തു' "
            "-> person രമേശ്, credit_given. Punjabi: 'ਰਮੇਸ਼ ਨੂੰ 500 ਰੁਪਏ "
            "ਉਧਾਰ ਦਿੱਤੇ' -> person ਰਮੇਸ਼, credit_given. English: 'I gave "
            "Ramesh 500 rupees on credit' -> person Ramesh, credit_given. "
            "If required details are unclear or there is no completed transaction, "
            "return no transactions and ask one short clarification question in "
            "the speaker's language."
        )
        self.last_raw_response = None
        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=f"{prompt}\n\nTranscript: {transcript}",
                config=self._types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=_gemini_transaction_schema(),
                    temperature=0,
                ),
            )
        except (TimeoutError, OSError) as exc:
            raise ParserError(f"Gemini request failed: {exc}") from exc
        except Exception as exc:
            # The SDK exposes API failures through different subclasses across releases.
            raise ParserError(f"Gemini request failed: {exc}") from exc

        try:
            if not response.text:
                raise ValueError("Gemini returned an empty response")
            self.last_raw_response = response.text
            return ParseResult.model_validate_json(response.text)
        except (ValueError, ValidationError) as exc:
            raise ParserError(f"Gemini returned invalid parser JSON: {exc}") from exc

    def parse_query(self, transcript: str) -> QueryIntent | None:
        prompt = (
            "Classify shopkeeper ledger speech in Hinglish, Hindi, Marathi, Tamil, "
            "Telugu, Gujarati, Bengali, Kannada, Malayalam, Punjabi or English. "
            "Return customer_balance with the customer's name in its original "
            "script, today_credit, unpaid_since with the number of days, or "
            "not_query if this is not a ledger question. Do not infer missing "
            "details. Return JSON matching the supplied schema."
        )
        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=f"{prompt}\n\nTranscript: {transcript}",
                config=self._types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=QueryClassification,
                    temperature=0,
                ),
            )
            if not response.text:
                raise ValueError("Gemini returned an empty query response")
            classification = QueryClassification.model_validate_json(response.text)
        except (ValueError, ValidationError) as exc:
            raise ParserError(f"Gemini returned invalid query JSON: {exc}") from exc
        except Exception as exc:
            raise ParserError(f"Gemini query request failed: {exc}") from exc

        if classification.intent == "not_query":
            return None
        try:
            return QueryIntent(
                intent=classification.intent,
                person=classification.person,
                days=classification.days,
            )
        except ValidationError as exc:
            raise ParserError(f"Gemini returned an incomplete query: {exc}") from exc

    def scan_notebook(self, image_bytes: bytes, mime_type: str = "image/jpeg") -> ScanResult:
        if not image_bytes:
            raise ParserError("Notebook image is empty.")

        prompt = (
            "You are reading a photo of a handwritten udhaar/khata (ledger) notebook page. "
            "The page may be in Hindi, Marathi, Gujarati, English, or a mix of these languages. "
            "It typically has a table with columns like: Name, Amount (₹), Type (Udhar/Jama/Received/Given/Credit), "
            "Date, Notes/Item description, and optionally Status (Pending/Cleared). "
            "TASK: Extract EVERY data row from the table as a JSON object. "
            "Rules: "
            "1. 'Udhar' / 'Given' / 'credit' / 'udhaar' means money was given out → use type 'credit_given'. "
            "2. 'Jama' / 'Received' / 'payment' means money was received → use type 'payment_received'. "
            "3. Never invent names or amounts — only use what is clearly written. "
            "4. Convert Devanagari/native digits (०१२३...) to Arabic numerals. "
            "5. Keep names exactly as written (Hindi/English/mixed is fine). "
            "6. If a row is hard to read, still include it with confidence 'low'. "
            "7. For the date field, use the written date string (e.g. '09/11/2026') or null if absent. "
            "8. For the note field, use the Notes/item description column value. "
            "9. Ignore summary rows like 'Total Udhar', 'Total Jama', page headers, and footer text. "
            "Return a JSON object with a 'rows' array. Each element must have: "
            "person (string), amount (number > 0), type ('credit_given' or 'payment_received'), "
            "note (string), date (string or null), confidence ('low', 'medium', or 'high')."
        )

        # Use a plain dict schema to avoid Pydantic emitting "additionalProperties":false
        # which Gemini's API rejects with INVALID_ARGUMENT.
        schema = {
            "type": "OBJECT",
            "properties": {
                "rows": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "person": {"type": "STRING"},
                            "amount": {"type": "NUMBER"},
                            "type": {
                                "type": "STRING",
                                "enum": ["credit_given", "payment_received"],
                            },
                            "note": {"type": "STRING"},
                            "date": {"type": "STRING", "nullable": True},
                            "confidence": {
                                "type": "STRING",
                                "enum": ["low", "medium", "high"],
                            },
                        },
                        "required": ["person", "amount", "type", "note", "confidence"],
                    },
                }
            },
            "required": ["rows"],
        }

        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=[
                    prompt,
                    self._types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                ],
                config=self._types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=schema,
                    temperature=0,
                ),
            )
        except (TimeoutError, OSError) as exc:
            raise ParserError(f"Gemini request failed: {exc}") from exc
        except Exception as exc:
            raise ParserError(f"Gemini request failed: {exc}") from exc

        try:
            if not response.text:
                raise ValueError("Gemini returned an empty response")
            raw = json.loads(response.text)
            if not isinstance(raw, dict) or not isinstance(raw.get("rows"), list):
                raise ValueError("Gemini response must contain a rows array")
            valid_rows = []
            for item in raw.get("rows", []):
                if not isinstance(item, dict):
                    raise ValueError("Gemini returned a row that was not an object")
                if item.get("amount") is None:
                    continue
                valid_rows.append(ScanRow(**item))
            return ScanResult(rows=valid_rows, raw_response=response.text)
        except (ValueError, ValidationError) as exc:
            logging.info("Gemini notebook scan response: %s", response.text)
            raise ParserError(f"Gemini returned invalid scan JSON: {exc}") from exc


def _gemini_transaction_schema() -> dict:
    return {
        "type": "OBJECT",
        "properties": {
            "transactions": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "person": {"type": "STRING"},
                        "normalized_person": {"type": "STRING", "nullable": True},
                        "amount": {"type": "NUMBER", "nullable": True},
                        "type": {
                            "type": "STRING",
                            "enum": ["credit_given", "payment_received", "create_customer"],
                        },
                        "note": {"type": "STRING"},
                    },
                    "required": ["person", "amount", "type", "note"],
                },
            },
            "clarification_question": {"type": "STRING", "nullable": True},
        },
        "required": ["transactions", "clarification_question"],
    }


def _normalize_person(name: str) -> str:
    name = " ".join(name.strip().split()).rstrip(".,!?।")
    name = re.sub(r"\s*(?:ji|jee)\.?$", "", name, flags=re.IGNORECASE).strip()
    name = re.sub(
        r"\s*(?:कडून|च्या|चे|ची|चा|ला|ने|को|से)$",
        "",
        name,
    )
    name = re.sub(
        r"\s*(?:kadun|la|ne|ko|se)$",
        "",
        name,
        flags=re.IGNORECASE,
    )
    return name.strip()


def _normalize_note(note: str, person: str, amount: float | None) -> str:
    cleaned = " ".join(note.strip().split())
    if not cleaned:
        return ""
    cleaned = re.sub(rf"(?<!\w){re.escape(person)}(?!\w)", " ", cleaned, flags=re.I)
    note_amount, amount_tokens = _find_amount(cleaned)
    if note_amount is not None:
        for token in amount_tokens:
            cleaned = re.sub(
                rf"(?<!\w){re.escape(token)}(?!\w)",
                " ",
                cleaned,
                count=1,
                flags=re.I,
            )
    elif amount is not None:
        cleaned = re.sub(rf"(?<!\w){re.escape(str(amount))}(?!\w)", " ", cleaned)
    cleaned = re.sub(
        r"\b(?:ko|la|ne|se|kadun|rupaye|rupya|rupees|rupee|ka|ki|ke|aaj|kal|today|"
        r"yesterday|aur|ani|and|sirf)\b",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    return re.sub(r"[\s,.;:!?।]+", " ", cleaned).strip()[:80]


def parse_query_intent(transcript: str) -> QueryIntent | None:
    """Recognize Hindi, Marathi, and Hinglish ledger questions locally."""
    if not isinstance(transcript, str) or not transcript.strip():
        return None
    text = _normalize_rule_text(transcript.strip()).translate(
        str.maketrans("०१२३४५६७८९", "0123456789")
    )
    lowered = re.sub(r"[?!।,.]+", " ", text.lower())
    lowered = " ".join(lowered.split())

    unpaid = re.search(
        r"\b(?:kisne|kaun|किसने|कौन)\b.*?\b(\d{1,3})\s*(?:din|दिन)\b"
        r".*?\b(?:nahi|nahin|nhi|not|नहीं)\b",
        lowered,
    )
    if unpaid is None:
        unpaid = re.search(
            r"\b(\d{1,3})\s*(?:din|दिन)\b.*?"
            r"\b(?:kisne|kaun|किसने|कौन)\b.*?\b(?:nahi|nahin|nhi|not|नहीं)\b",
            lowered,
        )
    if unpaid:
        days = int(unpaid.group(1))
        if 1 <= days <= 365:
            return QueryIntent(intent="unpaid_since", days=days)

    today_words = ("aaj", "आज")
    credit_words = ("udhaar", "udhar", "उधार")
    if (
        any(word in lowered for word in today_words)
        and any(word in lowered for word in credit_words)
        and re.search(r"\b(?:kitna|kitni|कितना|कितनी)\b", lowered)
    ):
        return QueryIntent(intent="today_credit")

    balance = re.search(
        r"(.+?)\s+(?:ka|ki|ke|का|की|के)\s+"
        r"(?:(?:kitna|kitni|kitne|कितना|कितनी|कितने)\s+)?"
        r"(?:baaki|baki|balance|bacha|बाकी|बकाया)\b",
        lowered,
    )
    if balance is None:
        balance = re.search(
            r"(.+?)\s+(?:ka|ki|ke|का|की|के)\s+"
            r"(?:kitna|kitni|kitne|कितना|कितनी|कितने)\b",
            lowered,
        )
    if balance:
        person = _normalize_person(balance.group(1))
        person = re.sub(r"^(?:aur|and)\s+", "", person, flags=re.IGNORECASE)
        if person and person.lower() not in {"mera", "apna", "my"}:
            return QueryIntent(intent="customer_balance", person=person)
    return None


def _settings() -> tuple[str, str, float, Path]:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    model = os.getenv("PARSER_MODEL", "gemini-2.5-flash").strip()
    try:
        timeout = float(os.getenv("PARSER_TIMEOUT_SECONDS", "30"))
    except ValueError as exc:
        raise ParserError("PARSER_TIMEOUT_SECONDS must be a number.") from exc
    if timeout <= 0:
        raise ParserError("PARSER_TIMEOUT_SECONDS must be greater than 0.")
    cache_path = Path(
        os.getenv("PARSER_CACHE_PATH", str(ROOT / ".cache" / "parser.sqlite3"))
    ).expanduser()
    if not api_key:
        raise ParserError("GEMINI_API_KEY is not set in .env.")
    if not model:
        raise ParserError("PARSER_MODEL must not be empty.")
    return api_key, model, timeout, cache_path


def _default_provider() -> GeminiProvider:
    api_key, model, timeout, _ = _settings()
    return GeminiProvider(api_key, model, timeout)


def scan_notebook_image(
    image_bytes: bytes,
    mime_type: str = "image/jpeg",
    provider: GeminiProvider | None = None,
) -> ScanResult:
    if provider is None:
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        model = os.getenv("SCAN_MODEL", "gemini-3-flash-preview").strip()
        if not api_key:
            raise ParserError("GEMINI_API_KEY is not set in .env.")
        if not model:
            raise ParserError("SCAN_MODEL must not be empty.")
        active_provider = GeminiProvider(api_key, model, 60)
    else:
        active_provider = provider
    return active_provider.scan_notebook(image_bytes, mime_type=mime_type)


def parse_query_intent_for_language(
    transcript: str,
    language: str,
) -> QueryIntent | None:
    """Use local rules only for Hindi/Marathi/Hinglish; classify other languages with Gemini."""
    if language in {"hi-en", "hi-IN", "mr-IN"}:
        return parse_query_intent(transcript)
    if not isinstance(transcript, str) or not transcript.strip():
        return None

    provider = _default_provider()
    last_error = None
    for attempt in range(2):
        try:
            return provider.parse_query(transcript.strip())
        except ParserError as exc:
            last_error = exc
            if attempt == 0:
                time.sleep(0.2)
    raise ParserError(f"Gemini query parser failed after two attempts: {last_error}") from last_error


def _ensure_cache_schema(connection: sqlite3.Connection) -> None:
    exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'parser_cache'"
    ).fetchone()
    if exists:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(parser_cache)")
        }
        if "shop_id" not in columns:
            connection.execute("DROP TABLE parser_cache")
    connection.execute(
        """CREATE TABLE IF NOT EXISTS parser_cache (
            shop_id INTEGER NOT NULL,
            transcript_hash TEXT NOT NULL,
            response_json TEXT NOT NULL,
            cached_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (shop_id, transcript_hash)
        )"""
    )


def _cache_get(cache_path: Path, shop_id: int, transcript_hash: str):
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(cache_path, timeout=5)) as connection, connection:
            _ensure_cache_schema(connection)
            row = connection.execute(
                """SELECT response_json FROM parser_cache
                   WHERE shop_id = ? AND transcript_hash = ?""",
                (shop_id, transcript_hash),
            ).fetchone()
        return json.loads(row[0]) if row else None
    except (OSError, sqlite3.Error, json.JSONDecodeError) as exc:
        logging.warning("Could not read parser cache at %s: %s", cache_path, exc)
        return None


def _cache_put(
    cache_path: Path,
    shop_id: int,
    transcript_hash: str,
    result: dict,
) -> None:
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(cache_path, timeout=5)) as connection, connection:
            _ensure_cache_schema(connection)
            connection.execute(
                """INSERT OR REPLACE INTO parser_cache
                   (shop_id, transcript_hash, response_json) VALUES (?, ?, ?)""",
                (shop_id, transcript_hash, json.dumps(result, ensure_ascii=False)),
            )
    except (OSError, sqlite3.Error) as exc:
        logging.warning("Could not write parser cache at %s: %s", cache_path, exc)


def _transcript_hash(transcript: str, language: str = "") -> str:
    cache_key = f"{language}\0{transcript.strip()}"
    return hashlib.sha256(cache_key.encode("utf-8")).hexdigest()


def _as_transactions(
    result: ParseResult,
    *,
    low_confidence: bool = False,
) -> ParsedTransactions:
    if result.clarification_question:
        raise ParserClarification(result.clarification_question.strip())
    return ParsedTransactions(
        [
            transaction.model_dump(mode="json", exclude_none=True)
            for transaction in result.transactions
        ],
        low_confidence=low_confidence,
    )


def parse_with_provider(transcript: str, provider: ParserProvider) -> ParsedTransactions:
    """Parse with one provider, retrying once without enabling local fallback."""
    if not isinstance(transcript, str) or not transcript.strip():
        raise ValueError("transcript must be a non-empty string.")
    return _parse_with_retries(transcript.strip(), provider)


def _parse_with_retries(transcript: str, provider: ParserProvider) -> ParsedTransactions:
    last_error = None
    for attempt in range(2):
        try:
            return _as_transactions(provider.parse(transcript))
        except ParserClarification:
            raise
        except (ParserError, ValidationError) as exc:
            last_error = exc
            if attempt == 0:
                time.sleep(0.2)
    raise ParserError(f"Provider failed after two attempts: {last_error}") from last_error


def parse_transactions(
    transcript: str,
    provider: ParserProvider | None = None,
    *,
    cache: bool = True,
    shop_id: int = 0,
    language: str = "hi-en",
) -> ParsedTransactions:
    """Parse speech, retry the provider once, then use low-confidence local rules."""
    if not isinstance(transcript, str) or not transcript.strip():
        raise ValueError("transcript must be a non-empty string.")

    text = transcript.strip()
    cache_path = Path(
        os.getenv("PARSER_CACHE_PATH", str(ROOT / ".cache" / "parser.sqlite3"))
    ).expanduser()
    transcript_hash = _transcript_hash(text, language)
    if cache:
        cached = _cache_get(cache_path, shop_id, transcript_hash)
        if cached:
            question = cached.get("clarification_question")
            if isinstance(question, str) and question.strip():
                raise ParserClarification(question)
            try:
                cached_result = ParseResult.model_validate(
                    {
                        "transactions": cached["transactions"],
                        "clarification_question": None,
                    }
                )
                return _as_transactions(
                    cached_result,
                    low_confidence=cached.get("low_confidence", False),
                )
            except (KeyError, TypeError, ValidationError) as exc:
                logging.warning("Ignoring invalid parser cache entry: %s", exc)

    try:
        active_provider = provider if provider is not None else _default_provider()
        result = _parse_with_retries(text, active_provider)
    except ParserClarification as exc:
        if cache:
            _cache_put(
                cache_path,
                shop_id,
                transcript_hash,
                {"clarification_question": exc.question},
            )
        raise
    except ParserError as exc:
        if language not in {"hi-en", "hi-IN", "mr-IN"}:
            raise ParserError(
                f"Gemini could not parse this {language} transcript; local fallback "
                "supports only Hinglish, Hindi, and Marathi."
            ) from exc
        logging.warning("Gemini parser unavailable; using the rule-based parser: %s", exc)
        result = parse_fallback(text)

    if cache:
        _cache_put(
            cache_path,
            shop_id,
            transcript_hash,
            {
                "transactions": list(result),
                "low_confidence": result.low_confidence,
            },
        )
    return result


_DEVANAGARI_WORDS = {
    "आज": "aaj",
    "को": "ko",
    "ने": "ne",
    "से": "se",
    "के": "ke",
    "नाम": "naam",
    "खाता": "khata",
    "बनाओ": "banao",
    "बना": "bana",
    "खोलिए": "kholiye",
    "खोल": "khol",
    "दो": "do",
    "पाँच": "paanch",
    "पाच": "paanch",
    "पाँचशे": "panchshe",
    "सौ": "sau",
    "उधार": "udhaar",
    "दिए": "diye",
    "दिया": "diya",
    "दिये": "diye",
    "दिले": "dile",
    "परत": "parat",
    "जमा": "jama",
    "केले": "kele",
    "वापस": "wapas",
    "मिला": "mila",
    "मिले": "mila",
    "लिए": "liye",
    "पाचशे": "panchshe",
    "पाच": "paanch",
    "दीड": "dedh",
    "रुपये": "rupaye",
    "रुपए": "rupaye",
    "कितना": "kitna",
    "कितनी": "kitni",
    "कितने": "kitne",
    "बाकी": "baaki",
    "बकाया": "bakaya",
    "नहीं": "nahi",
    "दिन": "din",
    "किसने": "kisne",
    "कौन": "kaun",
    "का": "ka",
    "की": "ki",
    "के": "ke",
}
_NUMBER_VALUES = {
    "ek": 1,
    "aik": 1,
    "एक": 1,
    "do": 2,
    "don": 2,
    "dho": 2,
    "दो": 2,
    "teen": 3,
    "tin": 3,
    "तीन": 3,
    "char": 4,
    "चार": 4,
    "paanch": 5,
    "panch": 5,
    "पाँच": 5,
    "chhe": 6,
    "che": 6,
    "छह": 6,
    "saat": 7,
    "sat": 7,
    "सात": 7,
    "aath": 8,
    "आठ": 8,
    "nau": 9,
    "नौ": 9,
    "das": 10,
    "दस": 10,
    "bees": 20,
    "बीस": 20,
    "pachas": 50,
    "पचास": 50,
    "पाच": 5,
    "पाचशे": 500,
    "पंचशे": 500,
    "dedh": 1.5,
    "डेढ़": 1.5,
    "दीड": 1.5,
    "sava": 1.25,
    "sawa": 1.25,
    "सवा": 1.25,
    "panchshe": 500,
    "paanchshe": 500,
    "pachshe": 500,
}
_SCALE_VALUES = {
    "sau": 100,
    "she": 100,
    "शे": 100,
    "शं": 100,
    "hazar": 1000,
    "hazaar": 1000,
    "hajar": 1000,
    "हजार": 1000,
    "हज़ार": 1000,
    "lakh": 100000,
    "लाख": 100000,
    "crore": 10000000,
    "करोड़": 10000000,
}
_CREDIT_MARKERS = re.compile(
    r"\b(?:udhaar|udhar|credit)\b|\b(?:udhaar|udhar)\s+par\b", re.IGNORECASE
)
_PAYMENT_MARKERS = re.compile(
    r"\b(?:wapas|parat|chukaya|chukav|jama|vasool|mila|aale|received|payment)\b"
    r"|(?:मिळाले|घेतले|घेतलं)",
    re.IGNORECASE,
)
_MARATHI_GIVING_VERBS = re.compile(
    r"(?:दिले|दिलं|दिला|दिली|dile|dila)",
    re.IGNORECASE,
)
_TOKEN_PATTERN = re.compile(
    r"\d+(?:[.,]\d+)?|(?:[^\W\d_]|[\u0900-\u097F])+",
    re.UNICODE,
)
_LEADING_TIME = re.compile(r"^(?:(?:aaj|kal|today|yesterday)\s+)+", re.IGNORECASE)


def _normalize_rule_text(text: str) -> str:
    text = text.translate(str.maketrans("०१२३४५६७८९", "0123456789"))
    for devanagari, latin in _DEVANAGARI_WORDS.items():
        text = re.sub(
            rf"(?<![\w\u0900-\u097F]){re.escape(devanagari)}(?![\w\u0900-\u097F])",
            latin,
            text,
        )
    return text


def _number_at(tokens: list[str], start: int):
    token = tokens[start]
    if re.fullmatch(r"\d+(?:[.,]\d+)?", token):
        return float(token.replace(",", ".")), start + 1

    current = 0.0
    total = 0.0
    found = False
    index = start
    while index < len(tokens):
        word = tokens[index].lower().strip(".,!?")
        if word in _NUMBER_VALUES:
            current += _NUMBER_VALUES[word]
            found = True
        elif word in _SCALE_VALUES:
            scale = _SCALE_VALUES[word]
            base = current if current else 1
            if scale >= 1000:
                total += base * scale
                current = 0
            else:
                current = base * scale
            found = True
        else:
            break
        index += 1
    return (total + current, index) if found else (None, start)


def _find_amount(text: str) -> tuple[float | None, list[str]]:
    tokens = _TOKEN_PATTERN.findall(text)
    for index, token in enumerate(tokens):
        amount, end = _number_at(tokens, index)
        if amount is not None and amount > 0:
            return amount, tokens[index:end]
    return None, []


def _extract_person(clause: str) -> str | None:
    attached_suffix = re.search(
        r"([^\s\d]+?)(?:कडून|ला|ने|चा|ची|चे|च्या|को|से)(?=\s|[0-9])",
        clause,
    )
    if attached_suffix:
        person = _LEADING_TIME.sub("", attached_suffix.group(1).strip())
        person = re.sub(r"^(?:aur|ani|and)\s+", "", person, flags=re.IGNORECASE)
        person = _normalize_person(person)
        if person:
            return person

    patterns = (
        r"(.+?)\s+(?:ko|la)\b",
        r"(.+?)\s+(?:ne|se|kadun)\b",
        r"(.+?)\s+(?:kadun)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, clause, flags=re.IGNORECASE)
        if match:
            person = _LEADING_TIME.sub("", match.group(1).strip())
            person = re.sub(r"^(?:aur|ani|and)\s+", "", person, flags=re.IGNORECASE)
            person = _normalize_person(person)
            if person and person.lower() not in {"maine", "tine", "unhone", "they"}:
                return person
    return None


def _rule_parse(transcript: str) -> ParseResult:
    normalized = _normalize_rule_text(transcript)
    customer_match = re.search(
        r"(.+?)\s+ke\s+naam\s+se\s+khata\s+(?:banao|bana\s+do|khol\s+do|kholiye)\b",
        normalized,
        flags=re.IGNORECASE,
    )
    if customer_match:
        person = _normalize_person(customer_match.group(1))
        if person:
            return ParseResult(
                transactions=[
                    Transaction(
                        person=person,
                        amount=None,
                        type="create_customer",
                    )
                ],
                clarification_question=None,
            )

    clauses = re.split(r"\s+(?:aur|ani|and|then)\s+|[,;।]+", normalized, flags=re.IGNORECASE)
    transactions: list[Transaction] = []
    previous_person = None

    for clause in clauses:
        marathi_giving = bool(_MARATHI_GIVING_VERBS.search(clause))
        attached_recipient = bool(
            re.search(r"(?:ला)(?=\s|[0-9])", clause)
        )
        attached_payer = bool(
            re.search(r"(?:ने|कडून)(?=\s|[0-9])", clause)
        )
        marathi_payment = bool(
            re.search(
                r"(?:parat\s+dile|jama\s+kele|मिळाले|घेतले|घेतलं)",
                clause,
            )
        )
        credit = (
            bool(_CREDIT_MARKERS.search(clause))
            and bool(re.search(r"\b(?:diya|diye|dile|dila)\b", clause, re.IGNORECASE))
        ) or (attached_recipient and marathi_giving and not marathi_payment)
        payment = bool(_PAYMENT_MARKERS.search(clause)) or (
            not credit
            and bool(re.search(r"\bne\b.*\b(?:diya|diye)\b", clause, re.IGNORECASE))
        ) or (attached_payer and marathi_giving) or marathi_payment
        if not credit and not payment:
            continue

        amount, amount_tokens = _find_amount(clause)
        person = _extract_person(clause)
        if person is None and re.search(r"\b(?:tine|usne|unhone|she|he)\b", clause, re.I):
            person = previous_person
        if person is None or amount is None or (credit and payment):
            continue

        transaction_type = "credit_given" if credit else "payment_received"
        if transaction_type == "payment_received" and re.search(r"\bko\b", clause, re.I):
            continue
        note = re.sub(r"^[\s,]+|[\s,.!?]+$", "", clause)
        for token in amount_tokens:
            note = re.sub(rf"(?<!\w){re.escape(token)}(?!\w)", "", note, count=1, flags=re.I)
        note = re.sub(
            rf"{re.escape(person)}(?:कडून|ला|ने|चा|ची|चे|च्या|को|से)?",
            " ",
            note,
        )
        note = re.sub(
            r"\b(?:ko|la|ne|se|kadun|rupaye|rupya|rupees|rupee|ka|ki|ke|aaj|kal|today|"
            r"yesterday|aur|ani|and|sirf)\b|(?:रुपये|रुपए|ला|ने|कडून|चा|ची|चे|च्या|को|से)",
            " ",
            note,
            flags=re.IGNORECASE,
        )
        note = re.sub(rf"(?<!\w){re.escape(person)}(?!\w)", " ", note, flags=re.I)
        note = " ".join(note.split())
        note = note[:80].strip()
        transaction = Transaction(
            person=person,
            amount=amount,
            type=transaction_type,
            note=note or ("udhaar diya" if credit else "payment received"),
        )
        transactions.append(transaction)
        previous_person = person

    if transactions:
        return ParseResult(transactions=transactions, clarification_question=None)
    return ParseResult(
        transactions=[],
        clarification_question="कृपया व्यक्ति, रकम और लेन-देन की जानकारी स्पष्ट करें।",
    )


def parse_fallback(transcript: str) -> ParsedTransactions:
    """Run the local rule parser without contacting Gemini."""
    if not isinstance(transcript, str) or not transcript.strip():
        raise ValueError("transcript must be a non-empty string.")
    return _as_transactions(_rule_parse(transcript.strip()), low_confidence=True)
