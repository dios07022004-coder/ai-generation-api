"""Режимы: список, предпросмотр промта и hot-reload без рестарта сервиса."""
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.api.deps import get_api_key, require_internal_token
from app.db.session import SessionLocal
from app.models import ApiKey, SystemEvent
from app.services.mode_registry import registry
from app.services.prompt_builder import build_prompt

router = APIRouter(tags=["modes"])


class PreviewRequest(BaseModel):
    image_url: str | None = None
    user_id: str | None = None
    request_id: str | None = None
    metadata: dict = Field(default_factory=dict)


@router.get("/modes")
def list_modes(
    task_type: str | None = Query(default=None, pattern="^(photo|video)$"),
    _: ApiKey = Depends(get_api_key),
) -> dict:
    modes = registry.list(task_type)
    return {
        "count": len(modes),
        "modes": [
            {"id": m.id, "type": m.type, "enabled": m.enabled, "model": m.model}
            for m in modes
        ],
    }


@router.post("/modes/{mode_id}/preview")
def preview_mode(
    mode_id: str,
    body: PreviewRequest,
    _: ApiKey = Depends(get_api_key),
) -> dict:
    """Отрендерить промт режима на тестовых данных БЕЗ генерации.

    Инструмент для авторов промтов: сразу показывает итоговый промт и ловит
    ошибки шаблона (несуществующая переменная и т.п.) — не тратя GPU.
    """
    mode = registry.get(mode_id)
    context = {
        "image_url": body.image_url or "",
        "user_id": body.user_id,
        "request_id": body.request_id,
        "task_type": mode.type,
        "mode": mode.id,
        "metadata": body.metadata,
    }
    prompt, negative = build_prompt(mode, context)  # бросит 422 при ошибке шаблона
    return {
        "mode": mode.id,
        "model": mode.model,
        "workflow": mode.workflow,
        "params": mode.params,
        "prompt": prompt,
        "negative_prompt": negative,
    }


@router.post("/admin/modes/reload")
def reload_modes(_claims: dict = Depends(require_internal_token)) -> dict:
    """Перечитать YAML режимов и models.yaml без рестарта. Требует internal JWT."""
    count = registry.reload()
    with SessionLocal() as db:
        db.add(SystemEvent(source="api", event="modes_reloaded", data={"count": count}))
        db.commit()
    return {"status": "reloaded", "count": count}
