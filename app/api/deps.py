"""FastAPI-зависимости: аутентификация (API-ключ, internal JWT) и rate limiting."""
import jwt
from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AuthError
from app.core.security import verify_internal_token
from app.db.session import get_db
from app.models import ApiKey
from app.repositories import api_key_repo
from app.services import rate_limiter


def get_api_key(
    request: Request,
    db: Session = Depends(get_db),
) -> ApiKey:
    # Заголовок настраивается (API_KEY_HEADER), читаем напрямую из request.
    raw = request.headers.get(settings.API_KEY_HEADER)
    if not raw:
        raise AuthError(f"missing {settings.API_KEY_HEADER} header")
    key = api_key_repo.get_active_by_raw(db, raw)
    if key is None:
        raise AuthError("invalid, suspended or expired API key")
    return key


def client_ip(request: Request) -> str:
    fwd = request.headers.get("X-Forwarded-For")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else ""


def enforce_rate_limit(request: Request, api_key: ApiKey, user_id: str | None) -> None:
    """Полный rate limit с учётом user_id из тела запроса (вызывается в роуте)."""
    rate_limiter.enforce(
        api_key_id=api_key.id,
        user_id=user_id,
        ip=client_ip(request),
    )


def require_internal_token(request: Request) -> dict:
    """Защита служебных/админ-эндпоинтов internal JWT (Authorization: Bearer ...)."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise AuthError("missing internal bearer token")
    try:
        return verify_internal_token(auth[7:])
    except jwt.InvalidTokenError as e:
        raise AuthError(f"invalid internal token: {e}") from e
