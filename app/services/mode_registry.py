"""Реестр режимов генерации.

Режим = декларативный YAML-файл (см. config/modes/...). Код режимы не содержит —
только загружает, валидирует и отдаёт. Поддерживается hot-reload без рестарта
(эндпоинт /admin/modes/reload вызывает ModeRegistry.reload()).
"""
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.errors import NotFoundError, ValidationAppError
from app.core.logging import get_logger

logger = get_logger(__name__)


class ModeConfig(BaseModel):
    """Структура одного режима. Поля, помеченные комментарием, правит контент-менеджер."""

    id: str
    type: str                              # photo | video
    enabled: bool = True
    model: str                             # ключ из config/models.yaml
    workflow: str | None = None            # имя ComfyUI workflow (config/workflows/<name>.json)
    params: dict = Field(default_factory=dict)

    # --- то, что правится для каждого режима ---
    prompt_template: str = ""              # Jinja2-шаблон промта
    negative_prompt: str = ""

    # Параметры сохранения лица/референса (используются workflow'ом):
    preserve_face: bool = False
    reference_strength: float | None = None


class ModelsConfig:
    """Загрузка config/models.yaml — какие модели стоят за логическими именами."""

    def __init__(self) -> None:
        self._models: dict = {}

    def load(self) -> None:
        path = Path(settings.MODELS_CONFIG)
        if not path.exists():
            logger.warning("models config not found", extra={"path": str(path)})
            self._models = {}
            return
        with path.open(encoding="utf-8") as f:
            self._models = yaml.safe_load(f) or {}

    def resolve(self, key: str) -> dict:
        """Вернуть настройки модели по логическому ключу."""
        return self._models.get(key, {})


class ModeRegistry:
    def __init__(self) -> None:
        self._modes: dict[str, ModeConfig] = {}
        self.models = ModelsConfig()

    def reload(self) -> int:
        """Перечитать все режимы и модели с диска. Возвращает число загруженных режимов."""
        self.models.load()
        modes: dict[str, ModeConfig] = {}
        base = Path(settings.MODES_DIR)
        if not base.exists():
            logger.error("modes dir not found", extra={"path": str(base)})
            self._modes = {}
            return 0

        for file in sorted(base.rglob("*.y*ml")):
            try:
                raw = yaml.safe_load(file.read_text(encoding="utf-8")) or {}
                mode = ModeConfig(**raw)
            except Exception as e:  # noqa: BLE001
                logger.error("invalid mode file", extra={"file": str(file), "error": str(e)})
                continue
            if mode.id in modes:
                logger.error("duplicate mode id", extra={"id": mode.id, "file": str(file)})
                continue
            modes[mode.id] = mode

        self._modes = modes
        logger.info("modes loaded", extra={"count": len(modes)})
        return len(modes)

    def get(self, mode_id: str) -> ModeConfig:
        mode = self._modes.get(mode_id)
        if mode is None:
            raise NotFoundError(f"mode '{mode_id}' not found")
        if not mode.enabled:
            raise ValidationAppError(f"mode '{mode_id}' is disabled")
        return mode

    def list(self, task_type: str | None = None) -> list[ModeConfig]:
        modes = list(self._modes.values())
        if task_type:
            modes = [m for m in modes if m.type == task_type]
        return sorted(modes, key=lambda m: m.id)


# Глобальный синглтон (в API и в воркере свой экземпляр, оба читают те же файлы).
registry = ModeRegistry()
