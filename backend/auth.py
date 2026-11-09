import base64
import hashlib
import hmac
import json
import secrets
import time

import bcrypt


SESSION_COOKIE = "awaaz_session"
SESSION_DURATION_SECONDS = 12 * 60 * 60


def hash_pin(pin: str) -> str:
    return bcrypt.hashpw(pin.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_pin(pin: str, pin_hash: str) -> bool:
    try:
        return bcrypt.checkpw(pin.encode("utf-8"), pin_hash.encode("ascii"))
    except (ValueError, TypeError):
        return False


def create_session_token(shop_id: int, secret: bytes, now: int | None = None) -> str:
    issued_at = int(time.time()) if now is None else now

    def encode(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")

    header = encode(b'{"alg":"HS256","typ":"JWT"}')
    payload = encode(json.dumps({
        "sub": str(shop_id),
        "iat": issued_at,
        "exp": issued_at + SESSION_DURATION_SECONDS,
    }, separators=(",", ":")).encode("utf-8"))
    message = f"{header}.{payload}".encode("ascii")
    signature = hmac.new(secret, message, hashlib.sha256).digest()
    return f"{header}.{payload}.{encode(signature)}"


def read_session_token(token: str, secret: bytes, now: int | None = None) -> int | None:
    try:
        header, payload, signature = token.split(".")
        message = f"{header}.{payload}".encode("ascii")
        expected = hmac.new(secret, message, hashlib.sha256).digest()

        def decode(value: str) -> bytes:
            return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))

        if not hmac.compare_digest(expected, decode(signature)):
            return None
        token_header = json.loads(decode(header))
        claims = json.loads(decode(payload))
        current_time = int(time.time()) if now is None else now
        shop_id = int(claims["sub"])
        if token_header != {"alg": "HS256", "typ": "JWT"}:
            return None
        if shop_id <= 0 or int(claims["exp"]) <= current_time:
            return None
        return shop_id
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        return None


def new_process_secret() -> bytes:
    return secrets.token_bytes(32)
