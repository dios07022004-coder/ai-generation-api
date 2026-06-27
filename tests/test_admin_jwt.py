"""Тесты защиты админ-эндпоинта internal JWT."""
from app.core.security import issue_internal_token


def test_reload_requires_token(client):
    assert client.post("/admin/modes/reload").status_code == 401


def test_reload_rejects_api_key(client):
    # Обычный API-ключ не подходит для админ-операции.
    r = client.post("/admin/modes/reload", headers={"X-API-Key": client.api_key})
    assert r.status_code == 401


def test_reload_with_valid_jwt(client):
    tok = issue_internal_token("ops", ttl_seconds=60)
    r = client.post("/admin/modes/reload", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    assert r.json()["count"] >= 45


def test_reload_rejects_garbage_jwt(client):
    r = client.post("/admin/modes/reload", headers={"Authorization": "Bearer not.a.jwt"})
    assert r.status_code == 401
