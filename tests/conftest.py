"""Герметичная тестовая среда: SQLite + fakeredis + Celery eager.

Позволяет гонять интеграционные тесты без поднятого PostgreSQL/Redis/воркера —
и локально, и в CI. Реальная генерация подменяется MockProvider.
"""
import os
import tempfile

# ВАЖНО: выставить окружение ДО импорта app.* (settings кешируется при импорте).
_TMP = tempfile.mkdtemp(prefix="aigen-test-")
os.environ.update(
    DATABASE_URL=f"sqlite:///{_TMP}/test.db",
    GENERATION_PROVIDER="mock",
    STORAGE_PROVIDER="local",
    STORAGE_LOCAL_DIR=_TMP,
    PUBLIC_BASE_URL="http://test",
    WEBHOOK_SIGNING_SECRET="test-secret",
    INTERNAL_JWT_SECRET="test-jwt",
    SAFETY_PROVIDER="mock",
)

import fakeredis  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    """Подменяем Redis (rate limiter + queue_size probe) на in-memory fake."""
    fake = fakeredis.FakeStrictRedis()
    import app.api.routes.health as health
    import app.services.rate_limiter as rl
    monkeypatch.setattr(rl, "_redis", fake)
    monkeypatch.setattr(health, "_broker", fake)
    return fake


@pytest.fixture(autouse=True)
def eager_celery():
    """Celery выполняет задачи синхронно в процессе теста."""
    from app.queues.celery_app import celery_app
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = False


@pytest.fixture
def db():
    """Чистая схема БД на каждый тест."""
    from app.db.session import engine
    from app.models import Base
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


def _make_key(callback_url: str | None = None) -> str:
    from app.core.security import generate_api_key
    from app.db.session import SessionLocal
    from app.models import ApiKey
    raw, key_hash = generate_api_key()
    with SessionLocal() as s:
        s.add(ApiKey(name="test", key_hash=key_hash, status="active", callback_url=callback_url))
        s.commit()
    return raw


@pytest.fixture
def make_key():
    """Фабрика API-ключей для тестов (возвращает raw-ключ)."""
    return _make_key


@pytest.fixture
def client(db):
    """TestClient с зарегистрированным API-ключом (в заголовке по умолчанию)."""
    from app.main import app
    raw = _make_key()
    with TestClient(app) as c:
        c.headers.update({"X-API-Key": raw})
        c.api_key = raw  # доступ к ключу из теста
        yield c
