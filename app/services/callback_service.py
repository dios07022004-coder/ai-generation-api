"""Отправка результата на сервер-источник (callback) с HMAC-подписью и ретраями.

Заголовки получателю:
  X-Webhook-Timestamp: <unix ts>
  X-Webhook-Signature: <hmac_sha256( "{ts}." + body )>
Проверка подписи описана в app/core/security.py:verify_signature.
"""
import json

import httpx
from tenacity import RetryError, retry, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import sign_payload
from app.db.session import SessionLocal
from app.models import Webhook

logger = get_logger(__name__)


def _post_once(url: str, body: bytes) -> int:
    ts, sig = sign_payload(body)
    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Timestamp": ts,
        "X-Webhook-Signature": sig,
    }
    with httpx.Client(timeout=30) as client:
        resp = client.post(url, content=body, headers=headers)
        resp.raise_for_status()
        return resp.status_code


def send_callback(task_id: str, url: str, payload: dict) -> bool:
    """Отправить callback с экспоненциальными ретраями. Лог доставки — в таблицу webhooks."""
    if not url:
        logger.warning("no callback url, skipping", extra={"task_id": task_id})
        return False

    body = json.dumps(payload, ensure_ascii=False).encode()

    with SessionLocal() as db:
        hook = Webhook(task_id=task_id, url=url, payload=payload, status="pending")
        db.add(hook)
        db.commit()
        db.refresh(hook)
        hook_id = hook.id

    attempts = {"n": 0}
    last_code = {"v": None}

    @retry(
        stop=stop_after_attempt(settings.CALLBACK_MAX_RETRIES),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        reraise=True,
    )
    def _do() -> int:
        attempts["n"] += 1
        code = _post_once(url, body)
        last_code["v"] = code
        return code

    try:
        code = _do()
        _finalize(hook_id, "delivered", attempts["n"], code, None)
        logger.info("callback delivered", extra={"task_id": task_id, "code": code})
        return True
    except (RetryError, httpx.HTTPError) as e:
        _finalize(hook_id, "failed", attempts["n"], last_code["v"], str(e))
        logger.error("callback failed", extra={"task_id": task_id, "error": str(e)})
        return False


def _finalize(hook_id: str, status: str, attempts: int, code: int | None, err: str | None) -> None:
    with SessionLocal() as db:
        hook = db.get(Webhook, hook_id)
        if hook:
            hook.status = status
            hook.attempts = attempts
            hook.response_code = code
            hook.last_error = err
            db.commit()
