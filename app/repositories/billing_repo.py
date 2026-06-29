"""Доступ к балансам и журналу биллинга. Только БД-операции, без бизнес-логики.

Транзакциями управляет вызывающий слой (app/services/billing.py): здесь только
flush, чтобы UniqueConstraint срабатывал сразу.
"""
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models import ApiKey, BillingLedger


def try_debit(db: Session, api_key_id: str, amount: int) -> bool:
    """Атомарно списать amount, только если хватает. True — успех, False — недостаточно.

    Условие balance >= amount проверяется под блокировкой строки самим UPDATE —
    гонок нет (без SELECT-then-UPDATE). Без RETURNING — путь одинаков для SQLite.
    """
    res = db.execute(
        update(ApiKey)
        .where(ApiKey.id == api_key_id, ApiKey.balance_credits >= amount)
        .values(balance_credits=ApiKey.balance_credits - amount)
    )
    return res.rowcount == 1


def credit(db: Session, api_key_id: str, amount: int) -> int:
    """Безусловно пополнить баланс (возврат/topup). Возвращает новый баланс."""
    db.execute(
        update(ApiKey)
        .where(ApiKey.id == api_key_id)
        .values(balance_credits=ApiKey.balance_credits + amount)
    )
    return get_balance(db, api_key_id)


def get_balance(db: Session, api_key_id: str) -> int:
    val = db.execute(
        select(ApiKey.balance_credits).where(ApiKey.id == api_key_id)
    ).scalar_one_or_none()
    return int(val) if val is not None else 0


def add_ledger(
    db: Session,
    api_key_id: str,
    entry_type: str,
    amount: int,
    balance_after: int,
    *,
    task_id: str | None = None,
    note: str | None = None,
) -> BillingLedger:
    row = BillingLedger(
        api_key_id=api_key_id,
        task_id=task_id,
        entry_type=entry_type,
        amount_credits=amount,
        balance_after=balance_after,
        note=note,
    )
    db.add(row)
    db.flush()  # UniqueConstraint(task_id, entry_type) сработает здесь (IntegrityError)
    return row


def ledger_exists(db: Session, task_id: str, entry_type: str) -> bool:
    return db.execute(
        select(BillingLedger.id).where(
            BillingLedger.task_id == task_id, BillingLedger.entry_type == entry_type
        )
    ).first() is not None


def list_ledger(
    db: Session,
    api_key_id: str,
    frm: datetime | None = None,
    to: datetime | None = None,
    limit: int = 200,
) -> list[BillingLedger]:
    stmt = select(BillingLedger).where(BillingLedger.api_key_id == api_key_id)
    if frm:
        stmt = stmt.where(BillingLedger.created_at >= frm)
    if to:
        stmt = stmt.where(BillingLedger.created_at <= to)
    stmt = stmt.order_by(BillingLedger.created_at.desc()).limit(limit)
    return list(db.execute(stmt).scalars().all())


def usage_summary(
    db: Session, api_key_id: str, frm: datetime | None = None, to: datetime | None = None
) -> dict:
    stmt = (
        select(
            BillingLedger.entry_type,
            func.count(),
            func.coalesce(func.sum(BillingLedger.amount_credits), 0),
        )
        .where(BillingLedger.api_key_id == api_key_id)
    )
    if frm:
        stmt = stmt.where(BillingLedger.created_at >= frm)
    if to:
        stmt = stmt.where(BillingLedger.created_at <= to)
    stmt = stmt.group_by(BillingLedger.entry_type)
    by_type = {et: {"count": int(c), "sum": int(s)} for et, c, s in db.execute(stmt)}
    holds = by_type.get("hold", {"count": 0, "sum": 0})
    refunds = by_type.get("refund", {"count": 0, "sum": 0})
    # holds.sum отрицательная (сумма -price); refunds.sum положительная.
    spent = -holds["sum"] - refunds["sum"]
    return {
        "generations_charged": holds["count"],
        "refunds": refunds["count"],
        "spent_credits": spent,
        "by_type": by_type,
    }
