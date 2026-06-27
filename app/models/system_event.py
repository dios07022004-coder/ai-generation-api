from sqlalchemy import JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, uuid_str


class SystemEvent(Base, TimestampMixin):
    """Системные события: старт/стоп, перезагрузка режимов, ошибки инфраструктуры."""

    __tablename__ = "system_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uuid_str)
    level: Mapped[str] = mapped_column(String(16), default="info")
    source: Mapped[str] = mapped_column(String(64))  # api | worker | scheduler
    event: Mapped[str] = mapped_column(String(64))
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
