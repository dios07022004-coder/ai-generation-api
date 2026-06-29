"""Журнал биллинга (ledger): все движения по балансам партнёров.

Каждая строка — одно движение: hold (списание при резерве), refund (возврат при
терминальном сбое), topup (пополнение), adjust (служебная/аудит, напр. фиксация
успешного списания с amount=0). Идемпотентность гарантируется UniqueConstraint
(task_id, entry_type): на одну задачу не может быть двух hold/refund/adjust.
"""
from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, uuid_str


class BillingLedger(Base, TimestampMixin):
    __tablename__ = "billing_ledger"
    __table_args__ = (
        UniqueConstraint("task_id", "entry_type", name="uq_ledger_task_entry"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uuid_str)
    api_key_id: Mapped[str] = mapped_column(
        ForeignKey("api_keys.id"), index=True, nullable=False
    )
    # null для topup/adjust без привязки к задаче:
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    # hold | refund | topup | adjust
    entry_type: Mapped[str] = mapped_column(String(16))
    # ЗНАКОВОЕ: hold = -price, refund = +price, topup = +amount, adjust = ±/0
    amount_credits: Mapped[int] = mapped_column(Integer)
    # Снимок баланса ПОСЛЕ этого движения:
    balance_after: Mapped[int] = mapped_column(Integer)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    def to_public(self) -> dict:
        return {
            "id": self.id,
            "entry_type": self.entry_type,
            "amount_credits": self.amount_credits,
            "balance_after": self.balance_after,
            "task_id": self.task_id,
            "note": self.note,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
