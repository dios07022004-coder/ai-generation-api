"""Юнит-тесты внутренних компонентов: промт, выключенный режим, storage."""
import pytest

from app.core.errors import NotFoundError, ValidationAppError
from app.services.mode_registry import ModeConfig, registry
from app.services.prompt_builder import build_prompt


def _ctx(**kw):
    base = {"image_url": "", "user_id": None, "request_id": None,
            "task_type": "photo", "mode": "X", "metadata": {}}
    base.update(kw)
    return base


def test_prompt_missing_variable_raises():
    mode = ModeConfig(id="X", type="photo", model="m", prompt_template="hi {{ metadata.absent }}")
    with pytest.raises(ValidationAppError):
        build_prompt(mode, _ctx())


def test_prompt_renders_metadata():
    mode = ModeConfig(id="X", type="photo", model="m",
                      prompt_template="a {{ metadata.x }} b", negative_prompt="neg")
    prompt, neg = build_prompt(mode, _ctx(metadata={"x": "CAT"}))
    assert prompt == "a CAT b"
    assert neg == "neg"


def test_disabled_mode_rejected(tmp_path, monkeypatch):
    # Подкладываем выключенный режим и проверяем, что registry.get его не отдаёт.
    registry.reload()
    registry._modes["DISABLED_X"] = ModeConfig(
        id="DISABLED_X", type="photo", model="m", enabled=False
    )
    with pytest.raises(ValidationAppError):
        registry.get("DISABLED_X")


def test_unknown_mode_raises():
    registry.reload()
    with pytest.raises(NotFoundError):
        registry.get("DOES_NOT_EXIST")


def test_local_storage_writes_file(tmp_path, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "STORAGE_LOCAL_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "PUBLIC_BASE_URL", "http://x")
    from app.storage.local import LocalStorage
    url = LocalStorage().save("a.png", b"data", "image/png")
    assert url == "http://x/files/a.png"
    assert (tmp_path / "a.png").read_bytes() == b"data"
