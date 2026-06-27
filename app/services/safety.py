"""Проверка безопасности контента ПЕРЕД генерацией (анти-CSAM, 21+).

Цель: не допускать генерацию по изображениям несовершеннолетних. Проверка
обязательна и запускается в воркере до вызова движка. При блокировке задача
немедленно падает (без ретраев), и на сервер-источник уходит failed-callback.

Провайдеры (SAFETY_PROVIDER):
  none        — выключено (только локальная разработка).
  mock        — для тестов: блокирует, если context["simulate_minor"] is truthy.
  insightface — реальная оценка возраста лица (нужны insightface + onnxruntime).
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class SafetyBlocked(Exception):
    """Контент заблокирован проверкой безопасности (не-retryable)."""


@dataclass
class SafetyResult:
    allowed: bool
    reason: str | None = None
    detected_age: float | None = None


class SafetyChecker(ABC):
    name = "base"
    needs_images = False  # нужно ли скачивать байты фото для проверки

    @abstractmethod
    def check(self, images: list[bytes], context: dict) -> SafetyResult:
        ...


class NoneSafetyChecker(SafetyChecker):
    name = "none"

    def check(self, images: list[bytes], context: dict) -> SafetyResult:
        return SafetyResult(allowed=True)


class MockSafetyChecker(SafetyChecker):
    """Тестовая проверка: блокирует по флагу в metadata."""

    name = "mock"
    needs_images = False

    def check(self, images: list[bytes], context: dict) -> SafetyResult:
        if context.get("simulate_minor"):
            return SafetyResult(False, reason="age_check_failed: minor detected (mock)",
                                detected_age=12.0)
        return SafetyResult(allowed=True)


class InsightFaceSafetyChecker(SafetyChecker):
    """Реальная оценка возраста по лицу (InsightFace buffalo_l).

    Прод: pip install insightface onnxruntime-gpu; модель скачивается при init.
    Блокирует, если на любом входном фото есть лицо младше SAFETY_MIN_AGE.
    """

    name = "insightface"
    needs_images = True

    def __init__(self) -> None:
        import numpy as np  # noqa: F401
        from insightface.app import FaceAnalysis
        self._app = FaceAnalysis(name="buffalo_l")
        self._app.prepare(ctx_id=0)  # GPU

    def check(self, images: list[bytes], context: dict) -> SafetyResult:
        import io

        import numpy as np
        from PIL import Image

        min_age = settings.SAFETY_MIN_AGE
        for data in images:
            try:
                img = Image.open(io.BytesIO(data)).convert("RGB")
                faces = self._app.get(np.array(img)[:, :, ::-1])  # RGB→BGR
            except Exception as e:  # noqa: BLE001
                if settings.SAFETY_FAIL_CLOSED:
                    return SafetyResult(False, reason=f"safety_check_error: {e}")
                continue
            for f in faces:
                age = float(getattr(f, "age", 99))
                if age < min_age:
                    return SafetyResult(
                        False,
                        reason=f"age_check_failed: detected age ~{age:.0f} < {min_age}",
                        detected_age=age,
                    )
        return SafetyResult(allowed=True)


def get_safety_checker() -> SafetyChecker:
    p = settings.SAFETY_PROVIDER
    if p == "insightface":
        return InsightFaceSafetyChecker()
    if p == "mock":
        return MockSafetyChecker()
    return NoneSafetyChecker()


def enforce_safety(image_urls: list[str], context: dict) -> None:
    """Скачать входные фото и проверить. Бросает SafetyBlocked при блокировке."""
    checker = get_safety_checker()
    if isinstance(checker, NoneSafetyChecker):
        return  # проверка выключена — не качаем зря

    images: list[bytes] = []
    if checker.needs_images:
        from app.services.image_fetch import load_bytes
        images = [b for b in (load_bytes(u) for u in image_urls if u) if b]
        # Нельзя проверить (фото не скачалось) при fail-closed = блокируем.
        if not images and settings.SAFETY_FAIL_CLOSED and any(image_urls):
            raise SafetyBlocked("safety_check_error: input image could not be loaded")

    result = checker.check(images, context)
    if not result.allowed:
        logger.warning("content blocked by safety", extra={"reason": result.reason})
        raise SafetyBlocked(result.reason or "content blocked")
