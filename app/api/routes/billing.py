"""Биллинг: баланс/использование для партнёра (X-API-Key) и управление для админа (internal JWT)."""
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_api_key, require_internal_token
from app.core.errors import NotFoundError
from app.db.session import get_db
from app.models import ApiKey
from app.repositories import billing_repo
from app.schemas.billing import (
    AdminBillingResponse,
    BalanceResponse,
    TopupRequest,
    TopupResponse,
    UsageResponse,
)
from app.services import billing

router = APIRouter(tags=["billing"])


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        from app.core.errors import ValidationAppError
        raise ValidationAppError(f"invalid datetime: {value!r}") from None


# --- Партнёр (X-API-Key): видит только свои данные ---

@router.get("/billing/balance", response_model=BalanceResponse)
def get_balance(
    db: Session = Depends(get_db),
    api_key: ApiKey = Depends(get_api_key),
) -> BalanceResponse:
    return BalanceResponse(balance_credits=billing_repo.get_balance(db, api_key.id))


@router.get("/billing/usage", response_model=UsageResponse)
def get_usage(
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = Query(default=None),
    db: Session = Depends(get_db),
    api_key: ApiKey = Depends(get_api_key),
) -> UsageResponse:
    frm, t = _parse_dt(from_), _parse_dt(to)
    entries = billing_repo.list_ledger(db, api_key.id, frm, t)
    summary = billing_repo.usage_summary(db, api_key.id, frm, t)
    return UsageResponse(summary=summary, entries=[e.to_public() for e in entries])


# --- Админ (internal JWT): пополнение и просмотр любого партнёра ---

@router.post("/admin/billing/{api_key_id}/topup", response_model=TopupResponse)
def topup(
    api_key_id: str,
    body: TopupRequest,
    db: Session = Depends(get_db),
    _claims: dict = Depends(require_internal_token),
) -> TopupResponse:
    new_balance = billing.topup(db, api_key_id, body.amount_credits, body.note)
    return TopupResponse(api_key_id=api_key_id, balance_credits=new_balance)


@router.get("/admin/billing/{api_key_id}", response_model=AdminBillingResponse)
def admin_view(
    api_key_id: str,
    db: Session = Depends(get_db),
    _claims: dict = Depends(require_internal_token),
) -> AdminBillingResponse:
    key = db.get(ApiKey, api_key_id)
    if key is None:
        raise NotFoundError("api key not found")
    return AdminBillingResponse(
        api_key_id=api_key_id,
        balance_credits=key.balance_credits,
        usage_summary=billing_repo.usage_summary(db, api_key_id),
        recent_ledger=[e.to_public() for e in billing_repo.list_ledger(db, api_key_id, limit=50)],
    )


@router.post("/admin/pricing/reload")
def reload_pricing(_claims: dict = Depends(require_internal_token)) -> dict:
    from app.services.pricing import pricing
    count = pricing.reload()
    return {"status": "reloaded", "count": count}
