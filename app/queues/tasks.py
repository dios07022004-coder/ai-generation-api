"""Celery-задача генерации: режим → промт → провайдер → storage → callback.

Надёжность:
  - автоматический retry с экспоненциальной задержкой;
  - soft/hard таймауты (см. celery_app);
  - при исчерпании ретраев — dead-letter (system_events) + failed-callback;
  - memory cleanup после каждой задачи (важно для GPU-воркера).
"""
import gc
import time

from celery import Task as CeleryTask
from celery.exceptions import SoftTimeLimitExceeded

from app.core.config import settings
from app.core.errors import ValidationAppError
from app.core.logging import get_logger
from app.db.session import SessionLocal
from app.models import Generation, SystemEvent
from app.monitoring.metrics import errors_total, generation_seconds, tasks_total
from app.providers.base import GenerationRequest
from app.providers.registry import get_provider
from app.queues.celery_app import celery_app
from app.repositories import task_repo
from app.services.mode_registry import registry
from app.services.prompt_builder import build_prompt
from app.services.safety import SafetyBlocked, enforce_safety
from app.storage.registry import get_storage

logger = get_logger(__name__)

# Реестр режимов в воркере загружается один раз при импорте модуля.
registry.reload()


def _progress_setter(task_id: str):
    def _set(p: int) -> None:
        with SessionLocal() as db:
            task_repo.update(db, task_id, progress=max(0, min(100, p)))
    return _set


@celery_app.task(
    bind=True,
    name="app.queues.tasks.process_generation",
    max_retries=settings.TASK_MAX_RETRIES,
    default_retry_delay=10,
    acks_late=True,
)
def process_generation(self: CeleryTask, task_id: str) -> None:
    started = time.monotonic()
    with SessionLocal() as db:
        task = task_repo.get(db, task_id)
        if task is None:
            logger.error("task not found", extra={"task_id": task_id})
            return
        snapshot = task.to_public()
        image_url = task.image_url
        reference_urls = list(task.reference_urls or [])
        driving_url = task.driving_url
        mask_url = task.mask_url
        mode_id = task.mode
        task_type = task.task_type
        meta = dict(task.meta or {})

    try:
        task_repo_update(task_id, status="processing", progress=0)

        # Безопасность: проверка возраста (21+) ДО любой генерации. Анти-CSAM.
        enforce_safety([image_url, *reference_urls], meta)

        mode = registry.get(mode_id)
        model_cfg = registry.models.resolve(mode.model)
        context = {
            "image_url": image_url,
            "user_id": snapshot.get("user_id"),
            "request_id": snapshot.get("request_id"),
            "task_type": task_type,
            "mode": mode_id,
            "metadata": meta,
        }
        prompt, negative = build_prompt(mode, context)

        provider = get_provider()
        gen_req = GenerationRequest(
            task_id=task_id,
            task_type=task_type,
            mode_id=mode_id,
            prompt=prompt,
            negative_prompt=negative,
            image_url=image_url,
            reference_urls=reference_urls,
            driving_url=driving_url,
            mask_url=mask_url,
            model={"name": mode.model, **model_cfg},
            workflow=mode.workflow,
            params=mode.params,
            preserve_face=mode.preserve_face,
            reference_strength=mode.reference_strength,
        )

        result = provider.generate(gen_req, _progress_setter(task_id))

        key = f"{task_id}.{result.ext}"
        url = get_storage().save(key, result.data, result.content_type)
        duration_ms = int((time.monotonic() - started) * 1000)

        with SessionLocal() as db:
            db.add(Generation(
                task_id=task_id, provider=provider.name, model=result.model,
                prompt=prompt, params=mode.params, result_url=url, duration_ms=duration_ms,
            ))
            db.commit()
            task_repo.update(
                db, task_id, status="completed", progress=100,
                result_url=url, error=None, generation_time_ms=duration_ms,
            )
            task_repo.add_log(db, task_id, "completed", data={"url": url, "ms": duration_ms})

        generation_seconds.labels(task_type=task_type).observe(duration_ms / 1000)
        tasks_total.labels(task_type=task_type, status="completed").inc()
        _send_success_callback(task_id, url, duration_ms, meta)

    except SafetyBlocked as e:
        # Контент заблокирован (напр. лицо младше 21) — без ретраев, сразу ошибка на источник.
        _fail_or_retry(self, task_id, f"content_blocked: {e}", retryable=False)
    except ValidationAppError as e:
        _fail_or_retry(self, task_id, f"validation_error: {e}", retryable=False)
    except SoftTimeLimitExceeded:
        _fail_or_retry(self, task_id, "soft time limit exceeded", retryable=False)
    except Exception as e:  # noqa: BLE001
        _fail_or_retry(self, task_id, f"{type(e).__name__}: {e}", retryable=True)
    finally:
        gc.collect()  # memory cleanup (на GPU-воркере критично между задачами)


def task_repo_update(task_id: str, **fields) -> None:
    with SessionLocal() as db:
        task_repo.update(db, task_id, **fields)


def _fail_or_retry(self: CeleryTask, task_id: str, error: str, *, retryable: bool) -> None:
    logger.warning("task error", extra={"task_id": task_id, "error": error,
                                        "retries": self.request.retries})
    with SessionLocal() as db:
        task_repo.update(db, task_id, retries=self.request.retries)
        task_repo.add_log(db, task_id, "error", level="error", message=error)

    if retryable and self.request.retries < settings.TASK_MAX_RETRIES:
        raise self.retry(exc=Exception(error),
                         countdown=min(60, 10 * (self.request.retries + 1)))

    # Ретраи исчерпаны → dead-letter + failed callback.
    _dead_letter(task_id, error)


def _dead_letter(task_id: str, error: str) -> None:
    errors_total.labels(where="generation").inc()
    with SessionLocal() as db:
        task_repo.update(db, task_id, status="failed", error=error)
        db.add(SystemEvent(level="error", source="worker", event="dead_letter",
                           message=error, data={"task_id": task_id}))
        db.commit()
        task = task_repo.get(db, task_id)
        callback_url = task.callback_url if task else None
        meta = dict(task.meta) if task and task.meta else {}

    if callback_url:
        from app.services.callback_service import send_callback
        send_callback(task_id, callback_url, {
            "task_id": task_id, "status": "failed", "error": error, "metadata": meta,
        })


def _send_success_callback(task_id: str, url: str, duration_ms: int, meta: dict) -> None:
    with SessionLocal() as db:
        task = task_repo.get(db, task_id)
        callback_url = task.callback_url if task else None
    if callback_url:
        from app.services.callback_service import send_callback
        send_callback(task_id, callback_url, {
            "task_id": task_id, "status": "completed", "result_url": url,
            "generation_time": duration_ms, "metadata": meta,
        })
