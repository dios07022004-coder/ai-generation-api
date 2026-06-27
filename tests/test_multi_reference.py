"""Контракт под мульти-персонажа и движения: несколько референсов + driving video."""


def test_multi_reference_and_driving_stored(client):
    from app.db.session import SessionLocal
    from app.models import Task

    body = {
        "task_type": "video", "mode": "VIDEO_VARIATION_1",
        "image_url": "https://example.com/main.jpg",
        "reference_urls": ["https://example.com/p2.jpg", "https://example.com/p3.jpg"],
        "driving_url": "https://example.com/drive.mp4",
        "request_id": "multi-1",
    }
    r = client.post("/generate", json=body)
    assert r.status_code == 202
    tid = r.json()["task_id"]

    with SessionLocal() as db:
        t = db.get(Task, tid)
        assert len(t.reference_urls) == 2
        assert "p2.jpg" in t.reference_urls[0]
        assert t.driving_url.endswith("drive.mp4")


def test_reference_urls_limit(client):
    body = {
        "task_type": "photo", "mode": "PHOTO_MODE_1",
        "reference_urls": [f"https://example.com/{i}.jpg" for i in range(9)],  # > 8
    }
    assert client.post("/generate", json=body).status_code == 422


def test_defaults_empty_when_not_provided(client):
    from app.db.session import SessionLocal
    from app.models import Task

    r = client.post("/generate", json={"task_type": "photo", "mode": "PHOTO_MODE_1"})
    tid = r.json()["task_id"]
    with SessionLocal() as db:
        t = db.get(Task, tid)
        assert t.reference_urls == []
        assert t.driving_url is None
