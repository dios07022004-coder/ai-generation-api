"""GET /tasks/{task_id} — статус задачи (поллинг источником)."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_api_key
from app.core.errors import NotFoundError
from app.db.session import get_db
from app.models import ApiKey
from app.repositories import task_repo
from app.schemas.task import TaskStatus

router = APIRouter(tags=["tasks"])


@router.get("/tasks/{task_id}", response_model=TaskStatus)
def get_task(
    task_id: str,
    db: Session = Depends(get_db),
    api_key: ApiKey = Depends(get_api_key),
) -> TaskStatus:
    task = task_repo.get(db, task_id)
    if task is None:
        raise NotFoundError("task not found")
    # Источник видит только свои задачи.
    if task.api_key_id and task.api_key_id != api_key.id:
        raise NotFoundError("task not found")
    return TaskStatus(**task.to_public())
