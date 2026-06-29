"""Реестр цен (партнёрский биллинг).

Цена генерации = кредиты (1 кредит = 1 ₽), целое число. Источник — декларативный
config/pricing.yaml (hot-reload, как режимы) + переопределения на самом ключе
(ApiKey.price_overrides). Никогда не возвращает 0/бесплатно: если цена не задана —
бросает ValidationAppError (fail-closed).
"""
from pathlib import Path

import yaml

from app.core.config import settings
from app.core.errors import ValidationAppError
from app.core.logging import get_logger

logger = get_logger(__name__)


class PricingRegistry:
    def __init__(self) -> None:
        self._defaults: dict = {}
        self._modes: dict = {}
        self._api_keys: dict = {}

    def reload(self) -> int:
        """Перечитать config/pricing.yaml. Возвращает число заданных цен (defaults+modes)."""
        path = Path(settings.PRICING_CONFIG)
        if not path.exists():
            logger.warning("pricing config not found", extra={"path": str(path)})
            self._defaults, self._modes, self._api_keys = {}, {}, {}
            return 0
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception as e:  # noqa: BLE001
            logger.error("invalid pricing config", extra={"error": str(e)})
            self._defaults, self._modes, self._api_keys = {}, {}, {}
            return 0
        self._defaults = data.get("defaults") or {}
        self._modes = data.get("modes") or {}
        self._api_keys = data.get("api_keys") or {}
        count = len(self._defaults) + len(self._modes)
        logger.info("pricing loaded", extra={"count": count})
        return count

    def price_for(self, task_type: str, mode: str, api_key=None) -> int:
        """Вернуть цену в кредитах для (task_type, mode) с учётом переопределений.

        Приоритет: ApiKey.price_overrides[mode] → [task_type] →
        yaml api_keys[key][mode] → [task_type] → yaml modes[mode] → yaml defaults[task_type].
        Если цена нигде не задана — ValidationAppError (fail-closed).
        """
        # 1-2. Переопределение на самом ключе (БД) — самый высокий приоритет.
        if api_key is not None:
            ov = api_key.price_overrides or {}
            if mode in ov:
                return _as_int(ov[mode], mode)
            if task_type in ov:
                return _as_int(ov[task_type], mode)
            # 3-4. Переопределение по ключу из yaml.
            key_cfg = self._api_keys.get(api_key.id) or {}
            if mode in key_cfg:
                return _as_int(key_cfg[mode], mode)
            if task_type in key_cfg:
                return _as_int(key_cfg[task_type], mode)
        # 5. По режиму.
        if mode in self._modes:
            return _as_int(self._modes[mode], mode)
        # 6. По типу задачи.
        if task_type in self._defaults:
            return _as_int(self._defaults[task_type], mode)
        # 7. Цена не задана — отказ (никогда не бесплатно).
        raise ValidationAppError(f"no price configured for mode '{mode}' ({task_type})")


def _as_int(value, mode: str) -> int:
    try:
        price = int(value)
    except (TypeError, ValueError) as e:
        raise ValidationAppError(f"invalid price for mode '{mode}': {value!r}") from e
    if price <= 0:
        raise ValidationAppError(f"price for mode '{mode}' must be > 0, got {price}")
    return price


# Глобальный синглтон (в API и в воркере свой экземпляр, читают тот же файл).
pricing = PricingRegistry()
