"""Тесты предпросмотра промта (dry-run для авторов промтов)."""


def test_preview_renders(client, make_key):
    # Подменим шаблон режима на использующий metadata и проверим рендер.
    from app.services.mode_registry import registry
    registry.reload()
    registry.get("PHOTO_MODE_1").prompt_template = "portrait of {{ metadata.who }}"

    r = client.post("/modes/PHOTO_MODE_1/preview", json={"metadata": {"who": "queen"}})
    assert r.status_code == 200
    assert r.json()["prompt"] == "portrait of queen"


def test_preview_reports_template_error(client):
    from app.services.mode_registry import registry
    registry.reload()
    registry.get("PHOTO_MODE_2").prompt_template = "{{ metadata.missing }}"
    r = client.post("/modes/PHOTO_MODE_2/preview", json={"metadata": {}})
    assert r.status_code == 422  # ошибка шаблона видна сразу, без GPU


def test_preview_unknown_mode(client):
    assert client.post("/modes/NOPE/preview", json={}).status_code == 404
