"""POST /uploads — загрузка исходного изображения (binary), возвращает image_url.

Сценарий «пользователь прикрепил фото»: фронтенд/источник шлёт файл сюда,
получает image_url и затем передаёт его в POST /generate.
"""
import uuid

from fastapi import APIRouter, Depends, File, UploadFile

from app.api.deps import get_api_key
from app.core.errors import ValidationAppError
from app.models import ApiKey
from app.storage.registry import get_storage

router = APIRouter(tags=["uploads"])

_ALLOWED = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}
_MAX_BYTES = 25 * 1024 * 1024  # 25 МБ


@router.post("/uploads")
async def upload_image(
    file: UploadFile = File(...),
    _: ApiKey = Depends(get_api_key),
) -> dict:
    ext = _ALLOWED.get(file.content_type or "")
    if ext is None:
        raise ValidationAppError(f"unsupported content type: {file.content_type}")

    data = await file.read()
    if len(data) > _MAX_BYTES:
        raise ValidationAppError("file too large (max 25MB)")
    if not data:
        raise ValidationAppError("empty file")

    key = f"uploads/{uuid.uuid4().hex}.{ext}"
    url = get_storage().save(key, data, file.content_type)
    return {"image_url": url, "size": len(data), "content_type": file.content_type}
