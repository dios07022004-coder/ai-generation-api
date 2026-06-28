"""Провайдер ComfyUI — реальная генерация на собственном GPU.

Принцип: вся «логика» (как сохранять лицо: InstantID / IP-Adapter / PuLID,
какие ноды, какая модель) лежит в workflow-файле config/workflows/<name>.json,
экспортированном из ComfyUI (формат "Save (API Format)"). Код только:
  1) берёт workflow по имени из режима,
  2) подставляет в него prompt / negative / image_url / параметры,
  3) ставит в ComfyUI и забирает результат.

Сохранение лица настраивается в самом workflow (ноды InstantID/PuLID) —
никакой жёсткой логики в коде нет, как и требует ТЗ.

Подстановка значений в workflow управляется "плейсхолдерами": в JSON-шаблоне
пиши строки вида "{{prompt}}", "{{negative}}", "{{image_url}}", "{{seed}}",
"{{param.width}}" и т.п. — они заменяются перед отправкой.
"""
import json
import re
import time
import uuid
from pathlib import Path

import httpx

from app.core.config import settings
from app.core.errors import ProviderError
from app.core.logging import get_logger

from .base import GenerationProvider, GenerationRequest, GenerationResult, ProgressCb

logger = get_logger(__name__)

_PLACEHOLDER = re.compile(r"\{\{\s*([\w.]+)\s*\}\}")


class ComfyUIProvider(GenerationProvider):
    name = "comfyui"

    def __init__(self) -> None:
        self.base = settings.COMFYUI_URL.rstrip("/")
        self.timeout = settings.COMFYUI_TIMEOUT
        self.workflows_dir = Path(settings.WORKFLOWS_DIR)

    # --- workflow ----------------------------------------------------------

    def _load_workflow(self, name: str, ctx: dict) -> dict:
        path = self.workflows_dir / f"{name}.json"
        if not path.exists():
            raise ProviderError(f"workflow '{name}' not found at {path}")
        raw = path.read_text(encoding="utf-8")

        def repl(m: re.Match) -> str:
            key = m.group(1)
            val = ctx
            for part in key.split("."):
                if isinstance(val, dict):
                    val = val.get(part)
                else:
                    val = None
                    break
            if val is None:
                return ""
            # JSON-экранируем значение (без внешних кавычек): корректно для строк
            # с переносами/кавычками внутри "..." И для чисел в позиции без кавычек.
            return json.dumps(str(val))[1:-1]

        substituted = _PLACEHOLDER.sub(repl, raw)
        try:
            return json.loads(substituted)
        except json.JSONDecodeError as e:
            raise ProviderError(
                f"workflow '{name}' is not valid JSON after substitution: {e}"
            ) from e

    def _upload_url(self, client: httpx.Client, url: str | None) -> str:
        """Скачать картинку по URL и загрузить в ComfyUI. Вернуть имя файла для LoadImage."""
        if not url:
            return ""
        from app.services.image_fetch import load_bytes
        data = load_bytes(url)
        if not data:
            return ""
        name = f"in_{uuid.uuid4().hex}.png"
        try:
            r = client.post(
                "/upload/image",
                files={"image": (name, data, "application/octet-stream")},
                data={"overwrite": "true"},
            )
            r.raise_for_status()
            return r.json().get("name", name)
        except httpx.HTTPError as e:
            raise ProviderError(f"comfyui image upload failed: {e}") from e

    # --- ComfyUI HTTP API --------------------------------------------------

    def generate(self, req: GenerationRequest, progress: ProgressCb) -> GenerationResult:
        if not req.workflow:
            raise ProviderError(f"mode '{req.mode_id}' has no 'workflow' set")

        ctx = {
            "prompt": req.prompt,
            "negative": req.negative_prompt,
            "image_url": req.image_url or "",
            "seed": req.params.get("seed", 0),
            "param": req.params,
            "model": req.model,
            "reference_strength": req.reference_strength or "",
            # Мульти-персонаж: {{reference_0}}, {{reference_1}}, ... и {{reference_count}}
            "reference_count": len(req.reference_urls),
            # Движения: управляющее видео/поза
            "driving_url": req.driving_url or "",
            # Редактирование: маска области
            "mask_url": req.mask_url or "",
        }
        for i, url in enumerate(req.reference_urls):
            ctx[f"reference_{i}"] = url

        with httpx.Client(base_url=self.base, timeout=self.timeout) as client:
            # Загружаем входные изображения в ComfyUI: нода LoadImage работает по
            # ИМЕНИ файла (а не URL). Имена доступны в workflow как {{image_name}},
            # {{mask_name}}, {{reference_0_name}}, ...
            ctx["image_name"] = self._upload_url(client, req.image_url)
            ctx["mask_name"] = self._upload_url(client, req.mask_url)
            for i, url in enumerate(req.reference_urls):
                ctx[f"reference_{i}_name"] = self._upload_url(client, url)

            workflow = self._load_workflow(req.workflow, ctx)
            try:
                r = client.post("/prompt", json={"prompt": workflow})
                r.raise_for_status()
                prompt_id = r.json()["prompt_id"]
            except (httpx.HTTPError, KeyError) as e:
                raise ProviderError(f"comfyui submit failed: {e}") from e

            progress(10)
            deadline = self.timeout
            interval = settings.COMFYUI_POLL_INTERVAL
            waited = 0.0
            while waited < deadline:
                time.sleep(interval)
                waited += interval
                try:
                    hist = client.get(f"/history/{prompt_id}").json()
                except httpx.HTTPError:
                    continue
                if prompt_id not in hist:
                    progress(min(90, 10 + int(waited)))
                    continue

                entry = hist[prompt_id]
                outputs = entry.get("outputs", {})
                file_info, ext, ctype = self._extract_output(outputs)
                if file_info is None:
                    # Достаём реальную ошибку ComfyUI (какая нода упала), а не общее «нет файла».
                    detail = ""
                    for m in entry.get("status", {}).get("messages", []):
                        if isinstance(m, list) and len(m) == 2 and m[0] == "execution_error":
                            d = m[1]
                            detail = f"{d.get('node_type')}: {d.get('exception_message')}"
                            break
                    raise ProviderError(f"comfyui error: {detail or 'no file output'}")

                data = self._download(client, file_info)
                progress(100)
                model_name = (req.model or {}).get("name") if isinstance(req.model, dict) else None
                return GenerationResult(data, ext, ctype, model=model_name)

        raise ProviderError("comfyui generation timed out")

    @staticmethod
    def _extract_output(outputs: dict):
        for node in outputs.values():
            if node.get("images"):
                info = node["images"][0]
                return info, "png", "image/png"
            if node.get("gifs"):  # видео-ноды (VHS) кладут результат в gifs
                info = node["gifs"][0]
                fmt = info.get("filename", "out.mp4").split(".")[-1].lower()
                ctype = "video/mp4" if fmt == "mp4" else f"image/{fmt}"
                return info, fmt, ctype
        return None, "", ""

    def _download(self, client: httpx.Client, info: dict) -> bytes:
        r = client.get("/view", params={
            "filename": info["filename"],
            "subfolder": info.get("subfolder", ""),
            "type": info.get("type", "output"),
        })
        r.raise_for_status()
        return r.content

    def health(self) -> bool:
        try:
            with httpx.Client(base_url=self.base, timeout=5) as client:
                return client.get("/system_stats").status_code == 200
        except httpx.HTTPError:
            return False
