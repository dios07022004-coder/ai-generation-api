"""Доступ к API-ключам."""
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_api_key
from app.models import ApiKey


def get_active_by_raw(db: Session, raw_key: str) -> ApiKey | None:
    """Найти активный, не истёкший ключ по сырому значению."""
    key = db.execute(
        select(ApiKey).where(ApiKey.key_hash == hash_api_key(raw_key))
    ).scalars().first()
    if key is None or key.status != "active":
        return None
    if key.expires_at and key.expires_at < datetime.now(UTC):
        key.status = "expired"
        db.commit()
        return None
    return key
