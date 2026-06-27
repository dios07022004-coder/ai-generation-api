"""Доступ к задачам и их логам."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Task, TaskLog


def create(db: Session, **fields) -> Task:
    task = Task(**fields)
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def get(db: Session, task_id: str) -> Task | None:
    return db.get(Task, task_id)


def get_by_request_id(db: Session, api_key_id: str | None, request_id: str) -> Task | None:
    stmt = select(Task).where(Task.request_id == request_id)
    if api_key_id:
        stmt = stmt.where(Task.api_key_id == api_key_id)
    return db.execute(stmt).scalars().first()


def update(db: Session, task_id: str, **fields) -> Task | None:
    task = db.get(Task, task_id)
    if task is None:
        return None
    for k, v in fields.items():
        setattr(task, k, v)
    db.commit()
    db.refresh(task)
    return task


def add_log(db: Session, task_id: str, event: str, *, level: str = "info",
            message: str | None = None, data: dict | None = None) -> None:
    db.add(TaskLog(task_id=task_id, event=event, level=level, message=message, data=data or {}))
    db.commit()
