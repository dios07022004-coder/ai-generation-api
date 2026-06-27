"""Тесты проверки безопасности 21+ перед генерацией и failed-callback при блоке."""
import pytest

from app.services.safety import MockSafetyChecker, SafetyBlocked, enforce_safety


def test_mock_checker_blocks_minor_flag():
    assert MockSafetyChecker().check([], {"simulate_minor": True}).allowed is False
    assert MockSafetyChecker().check([], {}).allowed is True


def test_enforce_safety_raises_on_minor():
    with pytest.raises(SafetyBlocked):
        enforce_safety([], {"simulate_minor": True})


def test_enforce_safety_passes_clean():
    enforce_safety([], {})  # не бросает


def test_generation_blocked_and_error_sent_back(client, make_key, monkeypatch):
    # Перехватываем отправку callback, чтобы проверить, что ошибка ушла на источник.
    import app.services.callback_service as cb
    captured = {}

    def fake_send(task_id, url, payload):
        captured["payload"] = payload
        captured["url"] = url
        return True

    monkeypatch.setattr(cb, "send_callback", fake_send)

    key = make_key(callback_url="https://src.example.com/cb")
    r = client.post(
        "/generate",
        headers={"X-API-Key": key},
        json={
            "task_type": "photo", "mode": "PHOTO_MODE_1",
            "image_url": "https://example.com/in.jpg",
            "metadata": {"simulate_minor": True}, "request_id": "blk-1",
        },
    )
    assert r.status_code == 202
    tid = r.json()["task_id"]

    # eager → задача уже упала на проверке безопасности
    st = client.get(f"/tasks/{tid}", headers={"X-API-Key": key}).json()
    assert st["status"] == "failed"
    assert "content_blocked" in st["error"]

    # ошибка отправлена обратно на сервер-источник
    assert captured["payload"]["status"] == "failed"
    assert "minor" in captured["payload"]["error"]
    assert captured["url"] == "https://src.example.com/cb"
