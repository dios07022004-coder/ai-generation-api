"""Рендеринг промтов из шаблонов режимов (Jinja2).

В шаблоне доступны переменные: image_url, user_id, request_id, task_type, mode,
metadata (объект). Пример шаблона:
    "portrait of {{ metadata.subject }}, keep the same face from reference"
"""
from jinja2 import Environment, StrictUndefined, TemplateError

from app.core.errors import ValidationAppError
from app.services.mode_registry import ModeConfig

# Undefined → ошибка: если в шаблоне есть переменная, которой нет в контексте,
# лучше явно упасть на этапе постановки задачи, чем сгенерировать мусор.
_env = Environment(undefined=StrictUndefined, autoescape=False)


def build_prompt(mode: ModeConfig, context: dict) -> tuple[str, str]:
    """Вернуть (prompt, negative_prompt), отрендеренные из шаблонов режима."""
    try:
        prompt = _env.from_string(mode.prompt_template).render(**context).strip()
        negative = _env.from_string(mode.negative_prompt).render(**context).strip()
    except TemplateError as e:
        raise ValidationAppError(f"prompt template error in mode '{mode.id}': {e}") from e
    return prompt, negative
