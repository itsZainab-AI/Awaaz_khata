import hashlib
import json
import logging
import os
import re
import sqlite3
import time
from abc import ABC, abstractmethod
from collections.abc import Iterable
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


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
    amount: float = Field(gt=0, allow_inf_nan=False)
    type: Literal["credit_given", "payment_received"]
    note: str

    @model_validator(mode="after")
    def normalize_fields(self):
        self.person = _normalize_person(self.person)
        self.note = self.note.strip()
        if not self.person:
            raise ValueError("person must contain a name")
        return self


class ParseResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    transactions: list[Transaction]
    clarification_question: str | None

    @model_validator(mode="after")
    def validate_result(self):
        has_question = bool(self.clarification_question and self.clarification_question.strip())
        if has_question == bool(self.transactions):
            raise ValueError("Return transactions or a clarification question, not both")
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

    def parse(self, transcript: str) -> ParseResult:
        prompt = (
            "Parse shopkeeper ledger speech in Hinglish, Hindi, or Marathi. "
            "Return every distinct completed transaction in speech order. "
            "credit_given means the shopkeeper gave goods or money on credit "
            "and the named person owes the shopkeeper. payment_received means "
            "the person paid or returned money to the shopkeeper. Convert spoken "
            "amounts to numeric rupees (paanch sau=500, dedh hazaar=1500, "
            "sava hazaar=1250, ek lakh=100000, ek crore=10000000). Remove "
            "honorifics such as ji/jee from names. Give each transaction a short "
            "contextual note. Never infer a missing person, amount, or direction. "
            "If required details are unclear or there is no completed transaction, "
            "return no transactions and ask one short clarification question in "
            "the speaker's language."
        )
        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=f"{prompt}\n\nTranscript: {transcript}",
                config=self._types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=ParseResult,
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
            return ParseResult.model_validate_json(response.text)
        except (ValueError, ValidationError) as exc:
            raise ParserError(f"Gemini returned invalid parser JSON: {exc}") from exc


def _normalize_person(name: str) -> str:
    name = " ".join(name.strip().split()).rstrip(".,!?।")
    return re.sub(r"\s*(?:ji|jee)\.?$", "", name, flags=re.IGNORECASE).strip()


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


def _cache_get(cache_path: Path, transcript_hash: str):
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(cache_path, timeout=5) as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS parser_cache (
                    transcript_hash TEXT PRIMARY KEY,
                    response_json TEXT NOT NULL,
                    cached_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )"""
            )
            row = connection.execute(
                "SELECT response_json FROM parser_cache WHERE transcript_hash = ?",
                (transcript_hash,),
            ).fetchone()
        return json.loads(row[0]) if row else None
    except (OSError, sqlite3.Error, json.JSONDecodeError) as exc:
        logging.warning("Could not read parser cache at %s: %s", cache_path, exc)
        return None


def _cache_put(cache_path: Path, transcript_hash: str, result: dict) -> None:
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(cache_path, timeout=5) as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS parser_cache (
                    transcript_hash TEXT PRIMARY KEY,
                    response_json TEXT NOT NULL,
                    cached_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )"""
            )
            connection.execute(
                """INSERT OR REPLACE INTO parser_cache (transcript_hash, response_json)
                   VALUES (?, ?)""",
                (transcript_hash, json.dumps(result, ensure_ascii=False)),
            )
    except (OSError, sqlite3.Error) as exc:
        logging.warning("Could not write parser cache at %s: %s", cache_path, exc)


def _transcript_hash(transcript: str) -> str:
    return hashlib.sha256(transcript.strip().encode("utf-8")).hexdigest()


def _as_transactions(
    result: ParseResult,
    *,
    low_confidence: bool = False,
) -> ParsedTransactions:
    if result.clarification_question:
        raise ParserClarification(result.clarification_question.strip())
    return ParsedTransactions(
        [transaction.model_dump(mode="json") for transaction in result.transactions],
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
) -> ParsedTransactions:
    """Parse speech, retry the provider once, then use low-confidence local rules."""
    if not isinstance(transcript, str) or not transcript.strip():
        raise ValueError("transcript must be a non-empty string.")

    text = transcript.strip()
    cache_path = Path(
        os.getenv("PARSER_CACHE_PATH", str(ROOT / ".cache" / "parser.sqlite3"))
    ).expanduser()
    transcript_hash = _transcript_hash(text)
    if cache:
        cached = _cache_get(cache_path, transcript_hash)
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
                transcript_hash,
                {"clarification_question": exc.question},
            )
        raise
    except ParserError as exc:
        logging.warning("Gemini parser unavailable; using the rule-based parser: %s", exc)
        result = parse_fallback(text)

    if cache:
        _cache_put(
            cache_path,
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
    "पाँच": "paanch",
    "पाच": "paanch",
    "पाँचशे": "panchshe",
    "सौ": "sau",
    "उधार": "udhaar",
    "दिए": "diye",
    "दिया": "diya",
    "दिये": "diye",
    "रुपये": "rupaye",
    "रुपए": "rupaye",
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
    "dedh": 1.5,
    "डेढ़": 1.5,
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
    r"\b(?:wapas|parat|chukaya|chukav|jama|vasool|mila|aale|received|payment)\b",
    re.IGNORECASE,
)
_TOKEN_PATTERN = re.compile(r"\d+(?:[.,]\d+)?|[^\W\d_]+", re.UNICODE)
_LEADING_TIME = re.compile(r"^(?:(?:aaj|kal|today|yesterday)\s+)+", re.IGNORECASE)


def _normalize_rule_text(text: str) -> str:
    for devanagari, latin in _DEVANAGARI_WORDS.items():
        text = re.sub(re.escape(devanagari), latin, text)
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
    clauses = re.split(r"\s+(?:aur|ani|and|then)\s+|[,;।]+", normalized, flags=re.IGNORECASE)
    transactions: list[Transaction] = []
    previous_person = None

    for clause in clauses:
        credit = bool(_CREDIT_MARKERS.search(clause)) and bool(
            re.search(r"\b(?:diya|diye|dile|dila)\b", clause, re.IGNORECASE)
        )
        payment = bool(_PAYMENT_MARKERS.search(clause)) or (
            not credit
            and bool(re.search(r"\bne\b.*\b(?:diya|diye)\b", clause, re.IGNORECASE))
        )
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
            r"\b(?:ko|la|ne|se|kadun|rupaye|rupya|rupees|rupee|ka|ki|ke)\b",
            " ",
            note,
            flags=re.IGNORECASE,
        )
        note = " ".join(note.split())
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
