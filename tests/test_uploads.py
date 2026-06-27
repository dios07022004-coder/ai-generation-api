"""Тесты загрузки изображения (POST /uploads)."""
import io

from PIL import Image


def _png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (32, 32), (10, 20, 30)).save(buf, format="PNG")
    return buf.getvalue()


def test_upload_png(client):
    r = client.post("/uploads", files={"file": ("a.png", _png_bytes(), "image/png")})
    assert r.status_code == 200
    body = r.json()
    assert body["image_url"].endswith(".png")
    assert body["size"] > 0


def test_upload_rejects_unsupported_type(client):
    r = client.post("/uploads", files={"file": ("a.txt", b"hello", "text/plain")})
    assert r.status_code == 422


def test_upload_requires_api_key(client):
    r = client.post("/uploads", headers={"X-API-Key": ""},
                    files={"file": ("a.png", _png_bytes(), "image/png")})
    assert r.status_code == 401
