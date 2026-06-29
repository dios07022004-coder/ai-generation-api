from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, uuid_str


class ApiKey(Base, TimestampMixin):
    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uuid_str)
    name: Mapped[str] = mapped_column(String(128))
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    # Куда слать callback по умолчанию для этого источника:
    callback_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    # active | suspended | expired
    status: Mapped[str] = mapped_column(String(16), default="active")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # --- Биллинг (партнёрская предоплата). Кредиты = ₽, только целые. ---
    balance_credits: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, server_default="0"
    )
    # Переопределение цены по этому партнёру: {"video": 35, "VIDEO_VARIATION_7": 45}
    price_overrides: Mapped[dict] = mapped_column(
        JSON, default=dict, nullable=False, server_default="{}"
    )

    def to_public(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status,
            "balance_credits": self.balance_credits,
        }
