"""Схемы запроса/ответа эндпоинта /generate."""
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


class GenerateRequest(BaseModel):
    task_type: Literal["photo", "video"]
    mode: str = Field(..., min_length=1, max_length=64)
    # Основной референс (лицо/персонаж).
    image_url: HttpUrl | None = None
    # Доп. референсы: другие персонажи / ракурсы (мульти-персонаж).
    reference_urls: list[HttpUrl] = Field(default_factory=list, max_length=8)
    # Управляющее видео/поза для переноса движений (motion-driven анимация).
    driving_url: HttpUrl | None = None
    user_id: str | None = Field(default=None, max_length=128)
    request_id: str | None = Field(default=None, max_length=128)
    # Если источник хочет переопределить callback per-request:
    callback_url: HttpUrl | None = None
    metadata: dict = Field(default_factory=dict)

    model_config = {"json_schema_extra": {"examples": [{
        "task_type": "photo",
        "mode": "PHOTO_MODE_1",
        "image_url": "https://example.com/in.jpg",
        "user_id": "u_123",
        "request_id": "req_abc",
        "metadata": {"any": "value"},
    }]}}


class GenerateAccepted(BaseModel):
    status: Literal["accepted"] = "accepted"
    task_id: str
