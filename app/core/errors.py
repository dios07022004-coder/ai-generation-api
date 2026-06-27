"""Доменные исключения и обработчики ошибок FastAPI."""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    """Базовая ошибка приложения."""

    status_code = 400
    code = "app_error"

    def __init__(self, message: str, *, code: str | None = None, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ValidationAppError(AppError):
    status_code = 422
    code = "validation_error"


class AuthError(AppError):
    status_code = 401
    code = "unauthorized"


class RateLimitError(AppError):
    status_code = 429
    code = "rate_limited"


class ProviderError(AppError):
    """Ошибка движка генерации (ComfyUI и т.п.)."""

    status_code = 502
    code = "provider_error"


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"status": "error", "error": {"code": exc.code, "message": exc.message}},
        )
