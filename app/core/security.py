"""Безопасность: хеш API-ключей, HMAC-подпись webhook'ов, internal JWT."""
import hashlib
import hmac
import secrets
import time

import jwt

from .config import settings

# --- API keys ---------------------------------------------------------------

def generate_api_key() -> tuple[str, str]:
    """Вернуть (raw_key, key_hash). raw отдаётся клиенту один раз, в БД — hash."""
    raw = "sk_" + secrets.token_urlsafe(32)
    return raw, hash_api_key(raw)


def hash_api_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def verify_api_key(raw: str, key_hash: str) -> bool:
    return hmac.compare_digest(hash_api_key(raw), key_hash)


# --- Webhook signature (HMAC-SHA256) ----------------------------------------

def sign_payload(body: bytes, *, timestamp: int | None = None) -> tuple[str, str]:
    """Подписать тело callback'а. Возвращает (timestamp, signature).

    Получатель проверяет: HMAC(secret, f"{ts}.{body}") == signature.
    """
    ts = str(timestamp or int(time.time()))
    mac = hmac.new(
        settings.WEBHOOK_SIGNING_SECRET.encode(),
        f"{ts}.".encode() + body,
        hashlib.sha256,
    )
    return ts, mac.hexdigest()


def verify_signature(body: bytes, timestamp: str, signature: str) -> bool:
    expected = hmac.new(
        settings.WEBHOOK_SIGNING_SECRET.encode(),
        f"{timestamp}.".encode() + body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


# --- Internal JWT (межсервисные / админ-операции) ---------------------------

def issue_internal_token(subject: str, *, ttl_seconds: int = 3600) -> str:
    """Выпустить internal JWT (HS256) для служебных вызовов (напр. reload режимов)."""
    now = int(time.time())
    payload = {
        "sub": subject,
        "scope": "internal",
        "iat": now,
        "exp": now + ttl_seconds,
    }
    return jwt.encode(payload, settings.INTERNAL_JWT_SECRET, algorithm="HS256")


def verify_internal_token(token: str) -> dict:
    """Проверить internal JWT. Бросает jwt.InvalidTokenError при невалидности."""
    payload = jwt.decode(token, settings.INTERNAL_JWT_SECRET, algorithms=["HS256"])
    if payload.get("scope") != "internal":
        raise jwt.InvalidTokenError("not an internal token")
    return payload
