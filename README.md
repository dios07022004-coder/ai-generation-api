# AI Generation API

Production-ориентированный API-сервис генерации **фото и видео** по режимам.
Генерация выполняется на **собственных GPU через ComfyUI** (self-hosted).
Сервис принимает запросы от серверов-источников, ставит задачи в очередь,
генерирует и отправляет результат обратно через callback.

> Запускается и без GPU: `GENERATION_PROVIDER=mock` рисует заглушку, чтобы
> весь пайплайн (API → очередь → воркер → callback) можно было разрабатывать
> и тестировать до подключения железа.

## Ключевая идея: режим = один файл

Вся бизнес-логика генерации вынесена в **декларативные режимы** — по одному
YAML-файлу на режим в `config/modes/`. Контент-менеджер правит **только промт
и параметры**, не трогая код:

```
config/modes/photo/PHOTO_MODE_1.yaml       # 5 фото-режимов
config/modes/video/VIDEO_VARIATION_1.yaml  # 40 видео-вариаций
```

Сохранение лица/персонажа/композиции задаётся в **ComfyUI workflow**
(`config/workflows/*.json`, ноды InstantID/IP-Adapter/PuLID) — тоже без кода.

Добавить режим = добавить файл. Обновить без перезапуска:
`POST /admin/modes/reload`.

## Архитектура

```
[Источник] → POST /generate → [API/FastAPI] → [Redis/Celery] → [Worker → ComfyUI/GPU]
                                   │                                    │
                             [PostgreSQL]                        [Storage: S3/R2/MinIO/local]
                                   │                                    │
                                   └──── callback (HMAC) ◀── результат ─┘
```

Полное ТЗ интеграции (2 сервера) + промтинг/качество — [docs/TZ.md](docs/TZ.md).
Запуск на Selectel (что брать + минимизация трат) — [docs/SELECTEL.md](docs/SELECTEL.md).
Деплой и правки через GitHub (бесплатный план) — [docs/GITHUB.md](docs/GITHUB.md).
Пошаговый запуск на GPU-сервере — [docs/RUNBOOK.md](docs/RUNBOOK.md).
Подключение сайта к API (промт для Cursor) — [docs/CURSOR_INTEGRATION.md](docs/CURSOR_INTEGRATION.md).
Онбординг AI-ассистента по самому API — [docs/AI_BRIEF.md](docs/AI_BRIEF.md).

Подробнее — [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md),
API — [docs/API_REFERENCE.md](docs/API_REFERENCE.md),
промтинг (где править) — [docs/PROMPTING.md](docs/PROMPTING.md),
редактирование изображений (ТЗ) — [docs/IMAGE_EDITING.md](docs/IMAGE_EDITING.md),
интеграция фронт→бэк + оплаты — [docs/INTEGRATION.md](docs/INTEGRATION.md),
нагрузка/задержки/очередь — [docs/CAPACITY.md](docs/CAPACITY.md),
ускорение генерации — [docs/OPTIMIZATION.md](docs/OPTIMIZATION.md),
деплой — [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

## Быстрый старт (Docker, без GPU)

```bash
cp .env.example .env
docker compose up --build           # поднимет postgres, redis, миграции, api, worker
```

Создать API-ключ источнику:

```bash
docker compose exec api python -m scripts.create_api_key "My Site" --callback https://site.com/cb
```

Проверка:

```bash
curl -X POST http://localhost:8000/generate \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <raw-key>" \
  -d '{"task_type":"photo","mode":"PHOTO_MODE_1","image_url":"https://picsum.photos/512","user_id":"u1","request_id":"r1"}'
# → {"status":"accepted","task_id":"..."}

curl http://localhost:8000/tasks/<task_id> -H "X-API-Key: <raw-key>"
```

Swagger: http://localhost:8000/docs

## Запуск без Docker

```bash
python -m venv .venv && .venv\Scripts\activate     # Windows
pip install -r requirements.txt
cp .env.example .env
alembic upgrade head

uvicorn app.main:app --reload                       # терминал 1: API
celery -A app.queues.celery_app worker -l info -Q generation   # терминал 2: воркер
```

## Подключение GPU (ComfyUI)

1. Поднять ComfyUI на GPU-сервере, загрузить модели и собрать workflow.
2. Экспортировать workflow (**Save API Format**) в `config/workflows/<name>.json`,
   расставив плейсхолдеры (см. `config/workflows/README.md`).
3. В режимах указать `workflow: <name>` и нужную `model`.
4. В `.env`: `GENERATION_PROVIDER=comfyui`, `COMFYUI_URL=http://<gpu-host>:8188`.
5. Воркер запускать на GPU-сервере; API — на отдельном дешёвом VPS.

## Структура

```
app/
  api/         маршруты и зависимости (auth, rate limit)
  core/        конфиг, логи, ошибки, безопасность
  db/          сессия БД
  models/      ORM (users, api_keys, tasks, task_logs, generations, webhooks, system_events)
  schemas/     Pydantic
  repositories/ доступ к данным
  services/    режимы, промты, задачи, callbacks, rate limit
  providers/   движки генерации (mock, comfyui)
  storage/     local, s3/r2/minio
  queues/      Celery (очередь, задача-воркер)
  monitoring/  метрики Prometheus
config/        models.yaml, modes/*, workflows/*
alembic/       миграции
scripts/       утилиты (создание API-ключа)
docs/          ARCHITECTURE, API_REFERENCE
```

## Дальнейшие этапы (вне текущего ядра)

Kubernetes-манифесты, Grafana-дашборды, CI/CD, multi-GPU autoscaling —
следующим этапом (ядро к ним готово: stateless API + горизонтальные воркеры).
