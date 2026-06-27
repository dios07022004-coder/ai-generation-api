"""Заглушка генерации без GPU — для разработки и интеграционных тестов.

Если в запросе есть image_url, mock РЕАЛЬНО берёт это изображение как основу
и накладывает баннер с режимом и промтом — чтобы было видно, что исходное фото
прошло весь путь (приём → переформирование → результат). Настоящая трансформация
с сохранением лица делается потом в ComfyUI; здесь — наглядная имитация.
"""
import hashlib
import io
import textwrap
import time

from PIL import Image, ImageDraw

from app.services.image_fetch import load_bytes

from .base import GenerationProvider, GenerationRequest, GenerationResult, ProgressCb


def _bg(text: str) -> tuple[int, int, int]:
    h = hashlib.sha256(text.encode()).digest()
    return h[0], h[1], h[2]


def _load_source_image(image_url: str | None) -> Image.Image | None:
    """Загрузить исходное фото общим загрузчиком (локальный диск или HTTP)."""
    data = load_bytes(image_url)
    if not data:
        return None
    try:
        return Image.open(io.BytesIO(data)).convert("RGB")
    except Exception:  # noqa: BLE001 — для заглушки фейл не критичен
        return None


def _banner(img: Image.Image, mode_id: str, prompt: str) -> Image.Image:
    """Наложить полупрозрачный баннер с режимом и промтом."""
    img = img.copy()
    d = ImageDraw.Draw(img, "RGBA")
    w, h = img.size
    bar_h = max(60, h // 6)
    d.rectangle([(0, h - bar_h), (w, h)], fill=(0, 0, 0, 160))
    text = f"[MOCK] {mode_id}\n" + "\n".join(textwrap.wrap(prompt or "", width=max(20, w // 10)))
    d.multiline_text((12, h - bar_h + 8), text, fill=(255, 255, 255))
    return img


def _placeholder(text: str, w: int, h: int, shift: int = 0) -> Image.Image:
    img = Image.new("RGB", (w, h), _bg(text))
    d = ImageDraw.Draw(img)
    for i in range(0, w, 40):
        d.line([(i + shift, 0), (i + shift, h)], fill=(255, 255, 255), width=1)
    body = "\n".join(textwrap.wrap(text or "(empty)", width=max(10, w // 14)))
    d.multiline_text((20, 20), f"[MOCK]\n{body}", fill=(255, 255, 255))
    return img


class MockProvider(GenerationProvider):
    name = "mock"

    def generate_image(self, req: GenerationRequest, progress: ProgressCb) -> GenerationResult:
        w = int(req.params.get("width", 1024))
        h = int(req.params.get("height", 1024))
        for p in (20, 50, 80):
            time.sleep(0.1)
            progress(p)

        src = _load_source_image(req.image_url)
        if src is not None:
            src.thumbnail((w, h))
            out = _banner(src, req.mode_id, req.prompt)
        else:
            out = _placeholder(req.prompt, w, h)
        progress(100)

        buf = io.BytesIO()
        out.save(buf, format="PNG")
        return GenerationResult(buf.getvalue(), "png", "image/png", model="mock")

    def generate(self, req: GenerationRequest, progress: ProgressCb) -> GenerationResult:
        if req.task_type == "video":
            return self._video(req, progress)
        return self.generate_image(req, progress)

    def _video(self, req: GenerationRequest, progress: ProgressCb) -> GenerationResult:
        w = int(req.params.get("width", 768))
        h = int(req.params.get("height", 768))
        n = min(int(req.params.get("num_frames", 24)), 48)
        fps = int(req.params.get("fps", 8))

        src = _load_source_image(req.image_url)
        if src is not None:
            src.thumbnail((w, h))
        frames = []
        for i in range(n):
            if src is not None:
                base = src.copy()
                # лёгкое «дыхание» кадра, чтобы было видео из фото
                zoom = 1.0 + 0.04 * (i / max(n - 1, 1))
                zw, zh = int(base.width * zoom), int(base.height * zoom)
                base = base.resize((zw, zh)).crop((0, 0, base.width, base.height))
                frames.append(_banner(base, req.mode_id, req.prompt))
            else:
                frames.append(_placeholder(req.prompt, w, h, shift=i * 8))
            progress(int((i + 1) / n * 100))
            time.sleep(0.01)

        buf = io.BytesIO()
        frames[0].save(
            buf, format="GIF", save_all=True, append_images=frames[1:],
            duration=int(1000 / max(fps, 1)), loop=0,
        )
        return GenerationResult(buf.getvalue(), "gif", "image/gif", model="mock")
