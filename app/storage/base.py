"""Интерфейс хранилища результатов."""
from abc import ABC, abstractmethod


class StorageProvider(ABC):
    @abstractmethod
    def save(self, key: str, data: bytes, content_type: str) -> str:
        """Сохранить байты по ключу (имени файла) и вернуть публичный URL."""
        ...
