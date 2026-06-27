"""Загрузка байтов изображения по URL.

Локальные ссылки вида .../files/<key> читаются прямо с диска (общий том воркера),
остальные — по HTTP. Используется safety-проверкой и mock-провайдером.
"""
from pathlib import Path
from urllib.parse import urlparse

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def load_bytes(url: str | None, *, timeout: int = 20) -> bytes | None:
    if not url:
        return None
    try:
        path = urlparse(url).path
        if "/files/" in path:
            key = path.split("/files/", 1)[1]
            local = Path(settings.STORAGE_LOCAL_DIR) / key
            if local.exists():
                return local.read_bytes()
        resp = httpx.get(url, timeout=timeout, follow_redirects=True)
        resp.raise_for_status()
        return resp.content
    except Exception as e:  # noqa: BLE001
        logger.warning("image_fetch failed", extra={"url": url, "error": str(e)})
        return None
