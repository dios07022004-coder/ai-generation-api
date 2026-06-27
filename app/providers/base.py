"""Интерфейс движка генерации.

Любой провайдер (mock, comfyui, и в будущем другие) реализует generate().
Вся бизнес-логика генерации (как сохранять лицо, какой workflow) живёт
в шаблонах режимов и workflow-файлах, НЕ в коде провайдера.
"""
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field

ProgressCb = Callable[[int], None]


@dataclass
class GenerationRequest:
    task_id: str
    task_type: str                 # photo | video
    mode_id: str
    prompt: str
    negative_prompt: str
    image_url: str | None
    model: dict                    # разрешённые настройки модели из models.yaml
    workflow: str | None           # имя ComfyUI workflow
    params: dict = field(default_factory=dict)
    preserve_face: bool = False
    reference_strength: float | None = None
    # Доп. референсы (мульти-персонаж) и управляющее видео (движения):
    reference_urls: list[str] = field(default_factory=list)
    driving_url: str | None = None
    # Маска области для редактирования (inpaint):
    mask_url: str | None = None


@dataclass
class GenerationResult:
    data: bytes
    ext: str                       # png | mp4 | gif ...
    content_type: str
    model: str | None = None


class GenerationProvider(ABC):
    name: str = "base"

    @abstractmethod
    def generate(self, req: GenerationRequest, progress: ProgressCb) -> GenerationResult:
        ...

    def health(self) -> bool:
        return True
