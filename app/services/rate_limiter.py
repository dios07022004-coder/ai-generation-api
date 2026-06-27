"""Rate limiting на Redis (sliding window через фиксированные окна-счётчики).

Лимиты независимы по: API-ключу, пользователю, IP. Настройки — в конфиге.
"""
import redis

from app.core.config import settings
from app.core.errors import RateLimitError

_redis = redis.Redis.from_url(settings.REDIS_URL)


def _hit(scope: str, identifier: str, limit: int, window: int) -> None:
    if not identifier:
        return
    # Окно = текущее время // window. Ключ живёт ровно окно.
    import time
    bucket = int(time.time()) // window
    key = f"ratelimit:{scope}:{identifier}:{bucket}"
    pipe = _redis.pipeline()
    pipe.incr(key)
    pipe.expire(key, window)
    count, _ = pipe.execute()
    if count > limit:
        raise RateLimitError(f"rate limit exceeded for {scope}")


def enforce(*, api_key_id: str | None, user_id: str | None, ip: str | None) -> None:
    w = settings.RATE_LIMIT_WINDOW_SECONDS
    _hit("api_key", api_key_id or "", settings.RATE_LIMIT_PER_API_KEY, w)
    _hit("user", user_id or "", settings.RATE_LIMIT_PER_USER, w)
    _hit("ip", ip or "", settings.RATE_LIMIT_PER_IP, w)
