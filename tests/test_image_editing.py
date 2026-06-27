"""Редактирование изображений: приём mask_url и его хранение/проброс."""


def test_mask_url_stored(client):
    from app.db.session import SessionLocal
    from app.models import Task

    r = client.post("/generate", json={
        "task_type": "photo", "mode": "PHOTO_MODE_1",
        "image_url": "https://example.com/src.jpg",
        "mask_url": "https://example.com/mask.png",
        "request_id": "edit-1",
    })
    assert r.status_code == 202
    tid = r.json()["task_id"]
    with SessionLocal() as db:
        t = db.get(Task, tid)
        assert t.mask_url.endswith("mask.png")


def test_mask_url_optional(client):
    from app.db.session import SessionLocal
    from app.models import Task

    r = client.post("/generate", json={"task_type": "photo", "mode": "PHOTO_MODE_1"})
    tid = r.json()["task_id"]
    with SessionLocal() as db:
        assert db.get(Task, tid).mask_url is None
