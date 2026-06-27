"""Видео и фото уходят в разные очереди Celery."""
from unittest.mock import MagicMock


def _enqueue_queue(client, monkeypatch, task_type, mode):
    import app.queues.tasks as tasks
    spy = MagicMock()
    monkeypatch.setattr(tasks.process_generation, "apply_async", spy)
    r = client.post("/generate", json={"task_type": task_type, "mode": mode})
    assert r.status_code == 202
    return spy.call_args.kwargs["queue"]


def test_photo_goes_to_generation(client, monkeypatch):
    assert _enqueue_queue(client, monkeypatch, "photo", "PHOTO_MODE_1") == "generation"


def test_video_goes_to_generation_video(client, monkeypatch):
    assert _enqueue_queue(client, monkeypatch, "video", "VIDEO_VARIATION_1") == "generation_video"
