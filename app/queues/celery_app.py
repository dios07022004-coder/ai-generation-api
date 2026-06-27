"""Celery-приложение. Запуск воркера:  celery -A app.queues.celery_app worker -l info"""
from celery import Celery
from celery.signals import worker_process_init
from kombu import Queue

from app.core.config import settings

celery_app = Celery(
    "aigen",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.queues.tasks"],
)

celery_app.conf.update(
    task_acks_late=True,                      # ack после выполнения (не теряем при падении)
    worker_prefetch_multiplier=1,             # по одной тяжёлой GPU-задаче на воркер
    task_reject_on_worker_lost=True,
    task_soft_time_limit=settings.TASK_SOFT_TIMEOUT,
    task_time_limit=settings.TASK_HARD_TIMEOUT,
    task_default_queue="generation",
    # Две очереди: лёгкие фото и тяжёлое видео — чтобы видео не блокировало фото.
    # Конкретная очередь выбирается в task_service по task_type (apply_async queue=...).
    task_queues=(
        Queue("generation"),
        Queue("generation_video"),
    ),
    result_expires=3600,
    broker_transport_options={"visibility_timeout": settings.TASK_HARD_TIMEOUT + 60},
    worker_send_task_events=True,
    task_send_sent_event=True,
)


@worker_process_init.connect
def _start_metrics_server(**_kwargs) -> None:
    """Поднять /metrics воркера (порт 9100) для Prometheus."""
    try:
        from prometheus_client import start_http_server
        start_http_server(9100)
    except OSError:
        # порт занят (несколько воркеров на ноде) — не критично
        pass
