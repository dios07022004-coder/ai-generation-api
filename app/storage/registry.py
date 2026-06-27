"""Выбор хранилища по настройке STORAGE_PROVIDER."""
from app.core.config import settings

from .base import StorageProvider
from .local import LocalStorage


def get_storage() -> StorageProvider:
    if settings.STORAGE_PROVIDER in ("s3", "r2", "minio"):
        from .s3 import S3Storage
        return S3Storage()
    return LocalStorage()
