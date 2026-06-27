"""Тесты реестра режимов и рендеринга промтов (без БД/Redis/GPU)."""
from app.services.mode_registry import registry
from app.services.prompt_builder import build_prompt


def test_modes_load():
    count = registry.reload()
    assert count >= 45  # 5 photo + 40 video
    assert any(m.id == "PHOTO_MODE_1" for m in registry.list("photo"))
    assert len(registry.list("video")) == 40


def test_get_mode_and_type():
    registry.reload()
    mode = registry.get("VIDEO_VARIATION_12")
    assert mode.type == "video"
    assert mode.enabled is True


def test_prompt_render_with_context():
    registry.reload()
    mode = registry.get("PHOTO_MODE_1")
    mode.prompt_template = "subject {{ metadata.subject }} from {{ image_url }}"
    prompt, _ = build_prompt(mode, {
        "image_url": "http://x/y.jpg", "metadata": {"subject": "cat"},
        "user_id": None, "request_id": None, "task_type": "photo", "mode": "PHOTO_MODE_1",
    })
    assert prompt == "subject cat from http://x/y.jpg"
