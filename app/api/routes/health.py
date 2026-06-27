"""Health/readiness и метрики."""
import redis
from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.core.config import settings
from app.core.logging import get_logger
from app.monitoring.metrics import queue_size
from app.services.mode_registry import registry

router = APIRouter(tags=["system"])
logger = get_logger(__name__)

# Очереди Celery (Redis-брокер хранит задачи в списках с именем очереди).
_QUEUES = ("generation", "generation_video")
_broker = redis.Redis.from_url(settings.CELERY_BROKER_URL)


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "provider": settings.GENERATION_PROVIDER}


@router.get("/ready")
def ready() -> dict:
    return {"status": "ready", "modes_loaded": len(registry.list())}


@router.get("/metrics")
def metrics() -> Response:
    # Обновляем queue_size из брокера на момент скрейпа.
    try:
        total = sum(_broker.llen(q) for q in _QUEUES)
        queue_size.set(total)
    except redis.RedisError as e:
        logger.warning("queue_size probe failed", extra={"error": str(e)})
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
