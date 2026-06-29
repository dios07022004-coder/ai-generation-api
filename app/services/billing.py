"""Бизнес-логика биллинга: резерв (списание), возврат, пополнение, аудит.

Состояния по задаче: hold (списание при резерве) → [успех: оставить + аудит] |
[терминальный сбой: refund]. Идемпотентность: task.price_credits фиксируется один
раз, а UniqueConstraint(task_id, entry_type) не даёт повторить hold/refund/adjust.
"""
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, PaymentRequiredError, ValidationAppError
from app.core.logging import get_logger
from app.models import ApiKey
from app.repositories import billing_repo, task_repo

logger = get_logger(__name__)


def reserve(db: Session, api_key: ApiKey, task_id: str, price: int) -> None:
    """Списать price с баланса партнёра и зафиксировать hold + task.price_credits.

    Всё в одной транзакции. Недостаточно средств → PaymentRequiredError (402).
    """
    if not billing_repo.try_debit(db, api_key.id, price):
        db.rollback()
        raise PaymentRequiredError("insufficient balance")
    try:
        bal = billing_repo.get_balance(db, api_key.id)
        billing_repo.add_ledger(
            db, api_key.id, "hold", -price, bal, task_id=task_id, note="reserve"
        )
        task = task_repo.get(db, task_id)
        if task is not None:
            task.price_credits = price
        db.commit()
    except IntegrityError:
        # Дубликат hold для этой задачи → откат (списание этого вызова отменяется,
        # ранее уже списано один раз). Не считаем ошибкой оплаты.
        db.rollback()
        logger.warning("reserve already recorded", extra={"task_id": task_id})


def refund(db: Session, task_id: str) -> None:
    """Вернуть списанное при ТЕРМИНАЛЬНОМ сбое. Идемпотентно (один refund на задачу)."""
    task = task_repo.get(db, task_id)
    if task is None or task.price_credits is None:
        return  # биллинг был выключен при создании — возвращать нечего
    if billing_repo.ledger_exists(db, task_id, "refund"):
        return
    try:
        new_bal = billing_repo.credit(db, task.api_key_id, task.price_credits)
        billing_repo.add_ledger(
            db, task.api_key_id, "refund", task.price_credits, new_bal,
            task_id=task_id, note="refund",
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        logger.warning("refund already recorded", extra={"task_id": task_id})


def commit_charge_audit(db: Session, task_id: str) -> None:
    """Зафиксировать успешное списание нулевой строкой 'adjust' (для отчётов). Баланс не меняет."""
    task = task_repo.get(db, task_id)
    if task is None or task.price_credits is None:
        return
    if billing_repo.ledger_exists(db, task_id, "adjust"):
        return
    try:
        bal = billing_repo.get_balance(db, task.api_key_id)
        billing_repo.add_ledger(
            db, task.api_key_id, "adjust", 0, bal, task_id=task_id, note="committed"
        )
        db.commit()
    except IntegrityError:
        db.rollback()


def topup(db: Session, api_key_id: str, amount: int, note: str | None = None) -> int:
    """Пополнить баланс партнёра (ручное начисление админом). Возвращает новый баланс.

    Игнорирует BILLING_ENABLED — можно пополнять заранее, до включения биллинга.
    """
    if amount <= 0:
        raise ValidationAppError("topup amount must be > 0")
    if db.get(ApiKey, api_key_id) is None:
        raise NotFoundError("api key not found")
    new_bal = billing_repo.credit(db, api_key_id, amount)
    billing_repo.add_ledger(db, api_key_id, "topup", amount, new_bal, note=note)
    db.commit()
    return new_bal
