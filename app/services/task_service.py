"""Бизнес-логика приёма задачи: валидация режима, идемпотентность, биллинг, очередь."""
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import PaymentRequiredError
from app.core.logging import get_logger
from app.models import ApiKey
from app.repositories import task_repo
from app.schemas.generate import GenerateRequest
from app.services.mode_registry import registry

logger = get_logger(__name__)


def create_task(db: Session, req: GenerateRequest, api_key: ApiKey | None) -> tuple[str, bool]:
    """Создать задачу и поставить в очередь. Возвращает (task_id, created_new).

    Идемпотентность: повторный request_id от того же ключа возвращает старую задачу.
    """
    # Режим должен существовать, быть включён и соответствовать task_type.
    mode = registry.get(req.mode)
    if mode.type != req.task_type:
        from app.core.errors import ValidationAppError
        raise ValidationAppError(
            f"mode '{req.mode}' is type '{mode.type}', not '{req.task_type}'"
        )

    api_key_id = api_key.id if api_key else None

    if req.request_id:
        existing = task_repo.get_by_request_id(db, api_key_id, req.request_id)
        if existing:
            return existing.id, False

    # Биллинг: считаем цену ДО создания задачи (нет цены → 422, без «осиротевшей» задачи).
    billing_on = settings.BILLING_ENABLED and api_key is not None
    price = None
    if billing_on:
        from app.services.pricing import pricing
        price = pricing.price_for(req.task_type, req.mode, api_key)

    callback_url = str(req.callback_url) if req.callback_url else (
        api_key.callback_url if api_key else None
    )

    task = task_repo.create(
        db,
        request_id=req.request_id,
        task_type=req.task_type,
        mode=req.mode,
        image_url=str(req.image_url) if req.image_url else None,
        reference_urls=[str(u) for u in req.reference_urls],
        driving_url=str(req.driving_url) if req.driving_url else None,
        mask_url=str(req.mask_url) if req.mask_url else None,
        user_id=req.user_id,
        api_key_id=api_key_id,
        callback_url=callback_url,
        meta=req.metadata,
        status="queued",
    )
    task_repo.add_log(db, task.id, "task_created", data={"mode": req.mode})

    # Биллинг: резервируем (списываем) средства до постановки в очередь.
    if billing_on:
        from app.services import billing
        try:
            billing.reserve(db, api_key, task.id, price)
        except PaymentRequiredError:
            task_repo.update(db, task.id, status="failed", error="insufficient_balance")
            logger.warning("insufficient balance", extra={"api_key_id": api_key_id})
            raise

    # Импорт здесь, чтобы API не тянул celery-воркер при импорте модуля.
    from app.queues.tasks import process_generation
    # Видео — в отдельную очередь, чтобы тяжёлые задачи не блокировали фото.
    queue = "generation_video" if req.task_type == "video" else "generation"
    process_generation.apply_async(args=[task.id], queue=queue)

    logger.info("task queued", extra={"task_id": task.id, "mode": req.mode, "queue": queue})
    return task.id, True
