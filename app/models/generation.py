from sqlalchemy import JSON, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, uuid_str


class Generation(Base, TimestampMixin):
    """Артефакт генерации (результат одного прогона провайдера)."""

    __tablename__ = "generations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uuid_str)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), index=True)
    provider: Mapped[str] = mapped_column(String(32))     # comfyui | mock | ...
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    result_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
