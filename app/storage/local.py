"""Локальное хранилище (диск). Файлы отдаёт API по /files/<key>."""
from pathlib import Path

from app.core.config import settings

from .base import StorageProvider


class LocalStorage(StorageProvider):
    def __init__(self) -> None:
        self.dir = Path(settings.STORAGE_LOCAL_DIR)
        self.dir.mkdir(parents=True, exist_ok=True)

    def save(self, key: str, data: bytes, content_type: str) -> str:
        path = self.dir / key
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
        return f"{settings.PUBLIC_BASE_URL.rstrip('/')}/files/{key}"
