from sqlalchemy import JSON, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, uuid_str


class Task(Base, TimestampMixin):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uuid_str)
    # request_id от источника — для идемпотентности
    request_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)

    task_type: Mapped[str] = mapped_column(String(16))   # photo | video
    mode: Mapped[str] = mapped_column(String(64))        # PHOTO_MODE_1 / VIDEO_VARIATION_12
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Доп. референсы (мульти-персонаж) и управляющее видео (движения):
    reference_urls: Mapped[list] = mapped_column(JSON, default=list)
    driving_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    user_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    api_key_id: Mapped[str | None] = mapped_column(ForeignKey("api_keys.id"), nullable=True)
    callback_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    meta: Mapped[dict] = mapped_column("metadata", JSON, default=dict)

    # queued | processing | completed | failed
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    result_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    retries: Mapped[int] = mapped_column(Integer, default=0)
    generation_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    def to_public(self) -> dict:
        return {
            "task_id": self.id,
            "request_id": self.request_id,
            "task_type": self.task_type,
            "mode": self.mode,
            "user_id": self.user_id,
            "status": self.status,
            "progress": self.progress,
            "result_url": self.result_url,
            "error": self.error,
            "generation_time": self.generation_time_ms,
            "metadata": self.meta,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
