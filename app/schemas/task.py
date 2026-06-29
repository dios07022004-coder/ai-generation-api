"""Схема статуса задачи."""
from pydantic import BaseModel


class TaskStatus(BaseModel):
    task_id: str
    request_id: str | None = None
    task_type: str
    mode: str
    status: str
    progress: int
    result_url: str | None = None
    error: str | None = None
    generation_time: int | None = None
    price_credits: int | None = None
    metadata: dict = {}
    created_at: str | None = None
    updated_at: str | None = None
