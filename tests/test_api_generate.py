"""Интеграционные тесты эндпоинта /generate и /tasks (полный цикл с eager-воркером)."""


def test_requires_api_key(client):
    # Запрос без ключа отклоняется.
    r = client.post("/generate", headers={"X-API-Key": ""},
                    json={"task_type": "photo", "mode": "PHOTO_MODE_1"})
    assert r.status_code == 401


def test_unknown_mode(client):
    r = client.post("/generate", json={"task_type": "photo", "mode": "NOPE"})
    assert r.status_code == 404


def test_type_mismatch(client):
    # PHOTO_MODE_1 — это photo, а просим как video.
    r = client.post("/generate", json={"task_type": "video", "mode": "PHOTO_MODE_1"})
    assert r.status_code == 422


def test_bad_task_type(client):
    r = client.post("/generate", json={"task_type": "audio", "mode": "PHOTO_MODE_1"})
    assert r.status_code == 422


def test_generate_completes_and_stores(client):
    r = client.post("/generate", json={
        "task_type": "photo", "mode": "PHOTO_MODE_1",
        "image_url": "https://example.com/a.jpg", "user_id": "u1", "request_id": "req-1",
    })
    assert r.status_code == 202
    task_id = r.json()["task_id"]

    # eager → задача уже выполнена.
    st = client.get(f"/tasks/{task_id}").json()
    assert st["status"] == "completed"
    assert st["progress"] == 100
    assert st["result_url"].endswith(".png")
    assert st["generation_time"] is not None


def test_idempotent_request_id(client):
    body = {"task_type": "photo", "mode": "PHOTO_MODE_1", "request_id": "dup-1"}
    a = client.post("/generate", json=body).json()["task_id"]
    b = client.post("/generate", json=body).json()["task_id"]
    assert a == b


def test_task_isolation_between_keys(client, make_key):
    # Задача одного ключа не видна под другим ключом.
    resp = client.post("/generate", json={"task_type": "photo", "mode": "PHOTO_MODE_1"})
    tid = resp.json()["task_id"]
    other = make_key()
    r = client.get(f"/tasks/{tid}", headers={"X-API-Key": other})
    assert r.status_code == 404


def test_video_mode_completes(client):
    r = client.post("/generate", json={"task_type": "video", "mode": "VIDEO_VARIATION_1"})
    assert r.status_code == 202
    st = client.get(f"/tasks/{r.json()['task_id']}").json()
    assert st["status"] == "completed"
    assert st["result_url"].endswith(".gif")
