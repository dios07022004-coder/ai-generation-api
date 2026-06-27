"""POST /generate — приём задачи от сервера-источника."""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import enforce_rate_limit, get_api_key
from app.db.session import get_db
from app.models import ApiKey
from app.monitoring.metrics import tasks_total
from app.schemas.generate import GenerateAccepted, GenerateRequest
from app.services import task_service

router = APIRouter(tags=["generation"])


@router.post("/generate", response_model=GenerateAccepted, status_code=202)
def generate(
    req: GenerateRequest,
    request: Request,
    db: Session = Depends(get_db),
    api_key: ApiKey = Depends(get_api_key),
) -> GenerateAccepted:
    # Rate limit с полным контекстом: по ключу, IP и пользователю (из тела).
    enforce_rate_limit(request, api_key, req.user_id)
    task_id, _created = task_service.create_task(db, req, api_key)
    tasks_total.labels(task_type=req.task_type, status="accepted").inc()
    return GenerateAccepted(task_id=task_id)
