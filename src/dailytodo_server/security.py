"""Password hashing and small signed token helpers."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError


password_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64decode(raw: str) -> bytes:
    padding = "=" * (-len(raw) % 4)
    return base64.urlsafe_b64decode(raw + padding)


def create_access_token(subject: str, secret_key: str, expires_delta: timedelta) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
        "typ": "access",
    }
    body = _b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(secret_key.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest()
    return f"{body}.{_b64encode(signature)}"


def decode_access_token(token: str, secret_key: str) -> dict[str, Any] | None:
    try:
        body, signature = token.split(".", 1)
    except ValueError:
        return None

    expected = hmac.new(secret_key.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest()
    try:
        provided = _b64decode(signature)
    except Exception:
        return None
    if not hmac.compare_digest(expected, provided):
        return None

    try:
        payload = json.loads(_b64decode(body))
    except Exception:
        return None
    if payload.get("typ") != "access":
        return None
    exp = payload.get("exp")
    if not isinstance(exp, int) or datetime.now(UTC).timestamp() >= exp:
        return None
    if not isinstance(payload.get("sub"), str):
        return None
    return payload
