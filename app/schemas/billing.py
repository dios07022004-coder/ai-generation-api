"""Схемы биллинг-эндпоинтов."""
from pydantic import BaseModel, Field


class BalanceResponse(BaseModel):
    balance_credits: int


class LedgerEntry(BaseModel):
    id: str
    entry_type: str
    amount_credits: int
    balance_after: int
    task_id: str | None = None
    note: str | None = None
    created_at: str | None = None


class UsageResponse(BaseModel):
    summary: dict
    entries: list[LedgerEntry]


class TopupRequest(BaseModel):
    amount_credits: int = Field(..., gt=0)
    note: str | None = None


class TopupResponse(BaseModel):
    api_key_id: str
    balance_credits: int


class AdminBillingResponse(BaseModel):
    api_key_id: str
    balance_credits: int
    usage_summary: dict
    recent_ledger: list[LedgerEntry]
