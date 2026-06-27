# Архитектура

## Компоненты

| Компонент | Роль | Масштабирование |
|---|---|---|
| **API (FastAPI)** | приём `/generate`, статусы, режимы | горизонтально (stateless) |
| **PostgreSQL** | задачи, ключи, логи, артефакты | вертикально + реплики чтения |
| **Redis** | брокер Celery, rate limit, кэш | кластер при росте |
| **Worker (Celery)** | генерация через провайдер | горизонтально, на GPU-серверах |
| **ComfyUI** | движок генерации на GPU | по числу GPU |
| **Storage** | результаты (S3/R2/MinIO/local) | внешнее |

## Поток запроса

1. Источник шлёт `POST /generate` с `X-API-Key`.
2. API: аутентификация ключа → rate limit → валидация режима/типа.
3. Идемпотентность по `request_id` (повтор возвращает ту же задачу).
4. Задача пишется в БД (`status=queued`) и кладётся в Celery.
5. API сразу отвечает `202 {status: accepted, task_id}`.
6. Воркер: режим → рендер промта (Jinja2) → провайдер (ComfyUI) → файл в Storage.
7. БД: `status=completed`, `result_url`, `generation_time`.
8. Callback на `callback_url` источника с HMAC-подписью (см. ниже).

## Почему Redis + Celery

- Зрелый стек, ack-late + visibility timeout → задачи не теряются при падении.
- Встроенные ретраи, soft/hard таймауты, маршрутизация по очередям.
- `prefetch_multiplier=1` — одна тяжёлая GPU-задача на воркер.
- RabbitMQ мощнее, но тяжелее в эксплуатации; Kafka — это лог событий,
  а не очередь задач. Для текущего профиля нагрузки Celery оптимален.

## Режимы (mode = файл)

`ModeRegistry` читает `config/modes/**/*.yaml` в память, валидирует через
Pydantic (`ModeConfig`). Hot-reload — `POST /admin/modes/reload`, без рестарта.
Промт рендерится из `prompt_template` (Jinja2) с контекстом запроса.
Логика генерации (в т.ч. сохранение лица) — в ComfyUI workflow, не в коде.

## Провайдеры генерации

Интерфейс `GenerationProvider.generate(req, progress)`:
- `MockProvider` — без GPU (разработка).
- `ComfyUIProvider` — подставляет плейсхолдеры в workflow и общается с ComfyUI.
- Заменяется переменной `GENERATION_PROVIDER` — ядро не меняется.

## Надёжность

- **Retry** — Celery (экспоненциальная задержка), `TASK_MAX_RETRIES`.
- **Dead-letter** — при исчерпании ретраев: `system_events` + failed-callback.
- **Timeout** — soft/hard лимиты задачи.
- **Webhook retry** — `tenacity`, лог в таблице `webhooks`.
- **Graceful shutdown** — lifespan FastAPI + ack-late у воркера.
- **Memory cleanup** — `gc.collect()` после каждой задачи (важно для GPU).

## Безопасность

- API-ключи: в БД только SHA-256 хеш; статусы active/suspended/expired.
- Rate limit: по ключу / пользователю / IP (Redis, окна).
- Callback подписывается HMAC-SHA256: заголовки `X-Webhook-Timestamp` и
  `X-Webhook-Signature = hmac(secret, "{ts}." + body)`. Источник обязан
  проверять подпись (`app/core/security.py:verify_signature`).
- Internal JWT-секрет заложен для межсервисных вызовов.

## GPU / масштабирование

- API не держит GPU — масштабируется по CPU.
- Воркеры запускаются на GPU-серверах (1 GPU = 1+ воркер, concurrency=1).
- Multi-GPU = больше воркеров/реплик; видео-нагрузку выносить в отдельную
  очередь и на отдельные воркеры.
- GPU-метрики (`gpu_usage`, `gpu_memory`) собирает dcgm-exporter на GPU-хосте.
