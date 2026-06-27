"""Выбор провайдера генерации по настройке GENERATION_PROVIDER."""
from app.core.config import settings

from .base import GenerationProvider
from .mock import MockProvider


def get_provider() -> GenerationProvider:
    if settings.GENERATION_PROVIDER == "comfyui":
        from .comfyui import ComfyUIProvider
        return ComfyUIProvider()
    return MockProvider()
