"""Тесты HMAC-подписи callback'ов, хеширования ключей и internal JWT."""
import jwt
import pytest

from app.core.security import (
    generate_api_key,
    issue_internal_token,
    sign_payload,
    verify_api_key,
    verify_internal_token,
    verify_signature,
)


def test_api_key_hash_roundtrip():
    raw, key_hash = generate_api_key()
    assert verify_api_key(raw, key_hash)
    assert not verify_api_key(raw + "x", key_hash)


def test_webhook_signature_roundtrip():
    body = b'{"task_id":"1","status":"completed"}'
    ts, sig = sign_payload(body)
    assert verify_signature(body, ts, sig)
    assert not verify_signature(body + b"x", ts, sig)


def test_internal_jwt_roundtrip():
    token = issue_internal_token("ops", ttl_seconds=60)
    claims = verify_internal_token(token)
    assert claims["sub"] == "ops"
    assert claims["scope"] == "internal"


def test_internal_jwt_expired():
    token = issue_internal_token("ops", ttl_seconds=-1)
    with pytest.raises(jwt.InvalidTokenError):
        verify_internal_token(token)
