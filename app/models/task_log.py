from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, uuid_str


class TaskLog(Base, TimestampMixin):
    __tablename__ = "task_logs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uuid_str)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), index=True)
    level: Mapped[str] = mapped_column(String(16), default="info")  # info | warning | error
    event: Mapped[str] = mapped_column(String(64))
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
