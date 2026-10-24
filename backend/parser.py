import os
import re
from typing import Literal

import requests
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


class ParserError(RuntimeError):
    """Raised when Ollama cannot return a valid transaction parse."""


class ParserClarification(RuntimeError):
    """Raised when a transcript needs clarification before ledger entry."""

    def __init__(self, question):
        self.question = question
        super().__init__(question)


class Transaction(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    person: str = Field(min_length=1)
    amount: float = Field(gt=0, allow_inf_nan=False)
    type: Literal["credit_given", "payment_received"]
    note: str

    @model_validator(mode="after")
    def validate_transaction(self):
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


def _normalize_person(name):
    name = " ".join(name.strip().split())
    name = name.rstrip(".,!?।")
    return re.sub(r"\s*(?:ji|jee)\.?$", "", name, flags=re.IGNORECASE).strip()


def _settings():
    load_dotenv()
    host = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
    model = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
    try:
        timeout = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "90"))
    except ValueError as exc:
        raise ParserError("OLLAMA_TIMEOUT_SECONDS must be a number.") from exc
    if timeout <= 0:
        raise ParserError("OLLAMA_TIMEOUT_SECONDS must be greater than 0.")
    return host, model, timeout


def parse_transactions(transcript):
    """Return validated transaction dictionaries, or raise for clarification."""
    if not isinstance(transcript, str) or not transcript.strip():
        raise ValueError("transcript must be a non-empty string.")

    host, model, timeout = _settings()
    system_prompt = (
        "You parse shopkeeper ledger speech in Hinglish, Hindi, and Marathi. "
        "Return only data matching the supplied JSON schema. Extract every "
        "distinct completed transaction, preserving speech order. A "
        "credit_given means the shopkeeper gave goods or money on credit, so "
        "the named person owes the shopkeeper. A payment_received means the "
        "person paid or returned money to the shopkeeper. Convert spoken "
        "amounts to numeric rupees (for example, paanch sau=500, dedh hazaar=1500, "
        "sava hazaar=1250, ek lakh=100000, ek crore=10000000). Remove honorifics "
        "such as ji/jee from names. Write a short note preserving the transaction "
        "context. Never infer a missing person, amount, or transaction direction. "
        "If any required detail is unclear, return no transactions and ask one "
        "short clarification question in the speaker's language. If the speech "
        "contains no completed transaction, ask what transaction should be recorded."
    )
    try:
        response = requests.post(
            f"{host}/api/chat",
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": transcript.strip()},
                ],
                "format": ParseResult.model_json_schema(),
                "stream": False,
                "options": {"temperature": 0},
            },
            timeout=timeout,
        )
        response.raise_for_status()
    except requests.Timeout as exc:
        raise ParserError(f"Ollama timed out after {timeout:g} seconds.") from exc
    except requests.ConnectionError as exc:
        raise ParserError(
            f"Cannot connect to Ollama at {host}. Start Ollama and pull model '{model}'."
        ) from exc
    except requests.RequestException as exc:
        detail = getattr(getattr(exc, "response", None), "text", "")
        raise ParserError(f"Ollama request failed: {detail[:400] or exc}") from exc

    try:
        content = response.json()["message"]["content"]
        result = ParseResult.model_validate_json(content)
    except (ValueError, KeyError, TypeError, ValidationError) as exc:
        raise ParserError(f"Ollama returned invalid parser JSON: {exc}") from exc

    if result.clarification_question:
        raise ParserClarification(result.clarification_question.strip())
    return [transaction.model_dump(mode="json") for transaction in result.transactions]