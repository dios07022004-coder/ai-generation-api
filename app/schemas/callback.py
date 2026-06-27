"""Схема payload'а, который уходит на сервер-источник (callback)."""
from typing import Literal

from pydantic import BaseModel


class CallbackSuccess(BaseModel):
    task_id: str
    status: Literal["completed"] = "completed"
    result_url: str
    generation_time: int | None = None
    metadata: dict = {}


class CallbackFailure(BaseModel):
    task_id: str
    status: Literal["failed"] = "failed"
    error: str
    metadata: dict = {}
