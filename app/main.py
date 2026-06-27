"""FastAPI-приложение: сборка, маршруты, жизненный цикл."""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.core.config import settings
from app.core.errors import register_error_handlers
from app.core.logging import get_logger, setup_logging
from app.db.session import SessionLocal
from app.models import SystemEvent
from app.monitoring.metrics import requests_total
from app.services.mode_registry import registry

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    count = registry.reload()
    logger.info("api startup", extra={"version": __version__, "modes": count})
    with SessionLocal() as db:
        db.add(SystemEvent(source="api", event="startup", data={"modes": count}))
        db.commit()
    yield
    # graceful shutdown
    logger.info("api shutdown")
    with SessionLocal() as db:
        db.add(SystemEvent(source="api", event="shutdown"))
        db.commit()


def create_app() -> FastAPI:
    app = FastAPI(
        title="AI Generation API",
        version=__version__,
        description="Генерация фото и видео по режимам (self-hosted GPU / ComfyUI).",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],          # в проде сузить до доменов источников
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_error_handlers(app)

    @app.middleware("http")
    async def _metrics_mw(request: Request, call_next):
        response = await call_next(request)
        # route.path даёт шаблон пути (с {param}) — низкая кардинальность меток.
        # Для статики (/files) и неизвестных путей огрубляем, чтобы не плодить серии.
        route = request.scope.get("route")
        path = getattr(route, "path", None)
        if not path:
            path = "/files/*" if request.url.path.startswith("/files/") else "other"
        requests_total.labels(
            method=request.method, path=path, status=response.status_code
        ).inc()
        return response

    from app.api.routes import generate, health, modes, tasks, uploads
    app.include_router(health.router)
    app.include_router(generate.router)
    app.include_router(uploads.router)
    app.include_router(tasks.router)
    app.include_router(modes.router)

    # Локальная отдача результатов (только для STORAGE_PROVIDER=local).
    if settings.STORAGE_PROVIDER == "local":
        os.makedirs(settings.STORAGE_LOCAL_DIR, exist_ok=True)
        app.mount("/files", StaticFiles(directory=settings.STORAGE_LOCAL_DIR), name="files")

    return app


app = create_app()
