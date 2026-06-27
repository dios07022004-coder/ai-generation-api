# Онбординг-промт для AI-ассистента (Cursor и т.п.)

> Скопируй ВЕСЬ текст ниже в Cursor/ассистента как контекст перед задачей.
> Внизу есть блок **[ЗАДАЧА]** — впиши туда, что нужно сделать (свои мысли).

---

Ты — senior backend/ML-инфра инженер, работаешь над проектом `ai-generation-api`.
Прежде чем писать код: прочитай этот бриф и соблюдай правила. Не ломай ключевые
принципы. Если правка затрагивает контракт/архитектуру — сначала кратко опиши план.

## Что это за проект
Self-hosted API генерации и редактирования **фото и видео** на собственном GPU.
Сервис-оркестратор: принимает запросы от внешнего «сервера-источника» (SRC),
ставит задачи в очередь, выполняет генерацию через ComfyUI, возвращает результат
callback'ом. Генерация умеет: сохранение лица (InstantID/PuLID), мульти-персонаж,
анимацию (i2v), редактирование (inpaint и т.п. — в планах).

## Стек
Python 3.12, FastAPI, Celery + Redis (очередь), PostgreSQL + SQLAlchemy 2.0 +
Alembic, Pydantic v2, Docker/Compose, ruff (линт), pytest. Движок генерации —
ComfyUI (HTTP), за абстракцией провайдера. Хранилище — local/S3/R2/MinIO.

## Архитектура (поток)
```
SRC → POST /generate (X-API-Key) → FastAPI → Redis/Celery → worker
        → GenerationProvider (mock | comfyui) → Storage → callback(HMAC) → SRC
```
Очереди раздельные: `generation` (фото) и `generation_video` (видео).

## ГЛАВНЫЙ ПРИНЦИП (не нарушать!)
Вся бизнес-логика генерации — **ДЕКЛАРАТИВНА**, не в коде:
- **Режим = YAML-файл** в `config/modes/photo|video/*.yaml`
  (поля: `id,type,enabled,model,workflow,params,prompt_template,negative_prompt,
  preserve_face,reference_strength`). Промты живут ТОЛЬКО здесь.
- **Workflow** генерации (как сохранять лицо, i2v, inpaint) — в
  `config/workflows/*.json` (экспорт ComfyUI), с плейсхолдерами
  `{{prompt}} {{negative}} {{image_url}} {{reference_0}} {{reference_count}}
  {{driving_url}} {{seed}} {{reference_strength}} {{param.<key>}} {{model.name}}`.
- **Модели** — `config/models.yaml` (логические имена → checkpoint/настройки).
НИКОГДА не зашивай промты/модели/«как генерировать» в Python. Новый режим = новый
YAML; новая логика — новый workflow. Движок один и общий.

## Карта кода
```
app/
  main.py                 сборка FastAPI, lifespan, middleware метрик, /files
  core/                   config (env), logging(JSON), errors, security(HMAC, JWT, api-key hash)
  api/deps.py             auth(X-API-Key), rate limit, require_internal_token
  api/routes/             generate, uploads, tasks, modes(+preview,+reload), health
  models/                 ORM: user, api_key, task, task_log, generation, webhook, system_event
  schemas/                Pydantic: generate(GenerateRequest), task, callback
  services/               mode_registry, prompt_builder(Jinja2), task_service,
                          callback_service(HMAC+retry), rate_limiter, safety, image_fetch
  providers/              base(GenerationRequest/Result), mock, comfyui, registry
  storage/                base, local, s3, registry
  queues/                 celery_app, tasks(process_generation: режим→промт→провайдер→storage→callback)
config/                   models.yaml, modes/*, workflows/*
alembic/                  миграции (0001 initial, 0002 multi_reference)
tests/                    pytest (герметичные: sqlite + fakeredis + celery eager)
docs/                     TZ, INTEGRATION, PROMPTING, IMAGE_EDITING, CAPACITY, OPTIMIZATION, SELECTEL, GITHUB, DEPLOYMENT, API_REFERENCE
```

## Контракт API (кратко)
- `POST /uploads` (multipart `file`, jpeg/png/webp ≤25MB) → `{image_url}`.
- `POST /generate` `{task_type:"photo"|"video", mode, image_url?, reference_urls?[≤8],
  driving_url?, user_id?, request_id?, callback_url?, metadata?}` → `202 {task_id}`.
- `GET /tasks/{id}` → статус. `GET /modes`, `POST /modes/{id}/preview`,
  `POST /admin/modes/reload` (Authorization: Bearer internal-JWT).
- Callback на SRC: заголовки `X-Webhook-Timestamp`, `X-Webhook-Signature =
  hmac_sha256(secret, "{ts}."+body)`; тело completed/failed.

## Что уже есть и работает (проверено: 41 тест, ruff clean, mock)
Очередь, идемпотентность (`request_id`), rate limit (key/user/ip), API-ключи
(active/suspended/expired), internal JWT для админки, мульти-референс
(`reference_urls`) + `driving_url`, загрузка файла, callbacks (HMAC + retry + DLQ),
**safety 21+ ПЕРЕД генерацией** (`SAFETY_PROVIDER=none|mock|insightface`,
блок → failed-callback), метрики Prometheus, Docker/K8s/CI.

## Что в планах (не реализовано)
- Реальные ComfyUI-workflow на GPU (сейчас провайдер `mock` рисует заглушку, но
  реально использует загруженное фото). См. `docs/PROMPTING.md`, `docs/TZ.md`.
- **Редактирование изображений**: добавить `mask_url` сквозь
  schema→model→миграция(0003)→provider→worker→comfyui + тесты. Точная спецификация —
  `docs/IMAGE_EDITING.md` §2.1. Делать СТРОГО по образцу `reference_urls`/`driving_url`.
- Реальная проверка возраста (`insightface`), Redis-кэш статусов, SSRF-валидация
  url, retention старых файлов.

## ПРАВИЛА работы (обязательны)
1. Соблюдай декларативный принцип (см. выше). Логику генерации — в YAML/workflow.
2. **Тесты должны оставаться зелёными** и линт чистым:
   `docker compose exec api sh -c "cd /app && pip install -q pytest fakeredis ruff && pytest -q && ruff check app tests"`.
   К новой фиче — добавляй тесты (герметичные, как в `tests/`).
3. Изменения API — **обратносовместимые** (новые поля опциональны).
4. Любое новое поле запроса проводи сквозь ВСЮ цепочку:
   `schemas/generate.py → models/task.py → alembic миграция → services/task_service.py
   → providers/base.py → queues/tasks.py → providers/comfyui.py(ctx) → tests`.
5. **Секреты не коммитить** (`.env` в .gitignore; в репо только `.env.example`).
   Большие модели ComfyUI в git не класть.
6. Ошибки задачи → всегда failed-callback на SRC (деньги возвращает SRC).
   Safety/validation — не-retryable; провайдер/таймаут — retryable.
7. Стиль: следуй существующим паттернам и комментариям (рус. комментарии в коде ок),
   ruff line-length 100, импорты сортированы, `raise ... from e` в except.
8. Запуск локально: `docker compose up -d --build` (api/worker/postgres/redis),
   провайдер по умолчанию `mock` (без GPU).

## Контекст развёртывания
Прод: проект на отдельном GPU-сервере (Selectel, напр. A5000/RTX4090 24GB),
SRC шлёт запросы из интернета. Биллинг/аккаунты — на SRC. Деплой через GitHub:
`git pull` + `docker compose up -d --build`; правка промтов — без рестарта через
`/admin/modes/reload`.

---

## [ЗАДАЧА]
<!-- ВПИШИ СЮДА, что нужно сделать. Примеры:
- "Реализуй mask_url для редактирования изображений по docs/IMAGE_EDITING.md §2.1, с тестами и миграцией 0003."
- "Добавь endpoint GET /generations с историей по user_id."
- "Собери ComfyUI workflow photo_instantid.json под сохранение лица (InstantID + ControlNet depth) и опиши параметры."
Опиши: цель, ожидаемое поведение, ограничения, критерии готовности. -->

(сюда — твои мысли)
