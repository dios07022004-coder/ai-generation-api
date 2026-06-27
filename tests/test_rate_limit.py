"""Тесты rate limiting (по пользователю / ключу / IP)."""
from unittest.mock import MagicMock


def test_user_rate_limit(client, monkeypatch):
    from app.core.config import settings
    # Низкий лимит по пользователю и не мешаем генерации (enqueue → no-op).
    monkeypatch.setattr(settings, "RATE_LIMIT_PER_USER", 2)
    import app.queues.tasks as tasks
    monkeypatch.setattr(tasks.process_generation, "apply_async", MagicMock())

    body = {"task_type": "photo", "mode": "PHOTO_MODE_1", "user_id": "heavy"}
    codes = [client.post("/generate", json={**body, "request_id": f"r{i}"}).status_code
             for i in range(4)]
    # Первые 2 проходят, далее — 429.
    assert codes[:2] == [202, 202]
    assert 429 in codes[2:]


def test_limit_is_per_user(client, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "RATE_LIMIT_PER_USER", 1)
    import app.queues.tasks as tasks
    monkeypatch.setattr(tasks.process_generation, "apply_async", MagicMock())

    # Разные пользователи не делят лимит.
    a = client.post("/generate", json={"task_type": "photo", "mode": "PHOTO_MODE_1",
                                       "user_id": "A", "request_id": "a1"}).status_code
    b = client.post("/generate", json={"task_type": "photo", "mode": "PHOTO_MODE_1",
                                       "user_id": "B", "request_id": "b1"}).status_code
    assert a == 202 and b == 202
