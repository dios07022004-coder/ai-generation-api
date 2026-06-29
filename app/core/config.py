"""Конфигурация сервиса из переменных окружения (.env)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    APP_ENV: str = "local"
    LOG_LEVEL: str = "INFO"

    # Generation provider
    GENERATION_PROVIDER: str = "mock"  # mock | comfyui
    COMFYUI_URL: str = "http://localhost:8188"
    COMFYUI_TIMEOUT: int = 600
    COMFYUI_POLL_INTERVAL: float = 0.5  # как часто опрашивать ComfyUI о готовности

    # Безопасность контента: проверка возраста ПЕРЕД генерацией (анти-CSAM).
    SAFETY_PROVIDER: str = "none"       # none | mock | insightface
    SAFETY_MIN_AGE: int = 21            # минимальный возраст лица на входном фото
    SAFETY_FAIL_CLOSED: bool = True     # при ошибке проверки — блокировать (безопаснее)

    # Database
    DATABASE_URL: str = "postgresql+psycopg://genapi:genapi@localhost:5432/genapi"

    # Redis / Celery
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # Mode / model config
    MODES_DIR: str = "./config/modes"
    WORKFLOWS_DIR: str = "./config/workflows"
    MODELS_CONFIG: str = "./config/models.yaml"

    # Storage
    STORAGE_PROVIDER: str = "local"  # local | s3 | r2 | minio
    STORAGE_LOCAL_DIR: str = "./storage"
    PUBLIC_BASE_URL: str = "http://localhost:8000"
    S3_ENDPOINT_URL: str = ""
    S3_REGION: str = "auto"
    S3_BUCKET: str = ""
    S3_ACCESS_KEY: str = ""
    S3_SECRET_KEY: str = ""
    S3_PUBLIC_URL: str = ""

    # Reliability
    TASK_SOFT_TIMEOUT: int = 540
    TASK_HARD_TIMEOUT: int = 600
    TASK_MAX_RETRIES: int = 3
    CALLBACK_MAX_RETRIES: int = 5

    # Security
    API_KEY_HEADER: str = "X-API-Key"
    WEBHOOK_SIGNING_SECRET: str = "change-me-in-production"
    INTERNAL_JWT_SECRET: str = "change-me-too"

    # Rate limit
    RATE_LIMIT_PER_API_KEY: int = 120
    RATE_LIMIT_PER_USER: int = 60
    RATE_LIMIT_PER_IP: int = 240
    RATE_LIMIT_WINDOW_SECONDS: int = 60

    # Billing (партнёрская оплата за генерацию). 1 кредит = 1 ₽, только целые.
    # По умолчанию ВЫКЛ — поведение не меняется, пока явно не включишь.
    BILLING_ENABLED: bool = False
    PRICING_CONFIG: str = "./config/pricing.yaml"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
