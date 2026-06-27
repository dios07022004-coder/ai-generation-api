# ТЗ: интеграция API генерации на любой сайт + промтинг и качество

Мастер-документ. Покрывает: топологию «отдельный сервер генерации ↔ сторонний
сервер-источник», развёртывание, безопасность между серверами, полный контракт
API, поток запроса, и подробно — **как менять промты и добиваться максимального
качества**.

Связанные документы: [API_REFERENCE](API_REFERENCE.md), [INTEGRATION](INTEGRATION.md)
(оплаты/аккаунты), [PROMPTING](PROMPTING.md), [CAPACITY](CAPACITY.md), [DEPLOYMENT](DEPLOYMENT.md).

---

## 0. Глоссарий

- **GEN-сервер** — отдельный сервер, где крутится ЭТОТ проект (FastAPI + Celery +
  Postgres + Redis + ComfyUI/GPU). Делает генерацию.
- **Источник (SRC)** — твой сайт/сервис (его бэкенд). Хранит пользователей,
  деньги, бизнес-логику. Шлёт запросы на GEN-сервер.
- **Фронтенд** — браузер пользователя. Общается ТОЛЬКО с SRC, не с GEN.
- **Режим (mode)** — декларативный YAML (PHOTO_MODE_x / VIDEO_VARIATION_x):
  промт + параметры + модель + workflow.
- **Workflow** — граф ComfyUI (`config/workflows/*.json`), реализующий саму
  генерацию (сохранение лица, i2v и т.п.).

---

## 1. Топология (два сервера)

```
[ Браузер ] ──HTTPS──> [ SRC: твой сайт-бэкенд ] ──HTTPS (X-API-Key)──> [ GEN: этот проект ]
   user UI               авторизация, баланс,                            FastAPI :8000
                         оплаты, прокси к GEN                            Celery worker
                              ▲                                          Postgres / Redis
                              │                                          ComfyUI :8188 (GPU)
                              └────── callback (HMAC, HTTPS) ────────────────────┘
```

Принципы:
- Фронт **никогда** не ходит напрямую в GEN и не знает его API-ключ.
- SRC ↔ GEN: только серверное HTTPS-взаимодействие с `X-API-Key` и HMAC-подписью
  callback'ов.
- GEN-сервер можно закрыть фаерволом так, чтобы `:8000` был доступен **только**
  с IP SRC-сервера (allowlist).

---

## 2. Развёртывание GEN-сервера (отдельная машина)

### 2.1 Требования
- Linux (Ubuntu 22.04+), Docker + Docker Compose.
- Для реальной генерации — GPU-нода (NVIDIA, драйверы + nvidia-container-toolkit)
  с ComfyUI. Без GPU можно запустить с `GENERATION_PROVIDER=mock` (заглушка) для
  интеграционного тестирования SRC↔GEN.
- Внешние managed-сервисы по желанию: PostgreSQL и Redis (или из compose).

### 2.2 Шаги
```bash
git clone <repo> && cd ai-generation-api
cp .env.example .env            # заполнить (см. 2.3)
docker compose up -d --build    # postgres, redis, migrate(alembic), api, worker
# создать API-ключ для SRC-сервера:
docker compose exec api python -m scripts.create_api_key "Site A" --callback https://src.example.com/api/gen-callback
# ⇒ ВЫДАСТ raw-ключ ОДИН раз — сохрани в секреты SRC.
```
Проверка: `curl https://gen.example.com/health` → `{"status":"ok",...}`.

### 2.3 Ключевые переменные `.env` (GEN)
| Переменная | Назначение |
|---|---|
| `GENERATION_PROVIDER` | `comfyui` (прод, GPU) или `mock` (тест без GPU) |
| `COMFYUI_URL` | адрес ComfyUI, напр. `http://comfyui:8188` |
| `DATABASE_URL` | PostgreSQL |
| `REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND` | Redis |
| `STORAGE_PROVIDER` | `r2`/`s3`/`minio`/`local` (для прода — R2/S3) |
| `S3_*`, `PUBLIC_BASE_URL` | хранилище и публичный домен файлов |
| `WEBHOOK_SIGNING_SECRET` | секрет HMAC-подписи callback (общий с SRC!) |
| `INTERNAL_JWT_SECRET` | секрет для админ-операций (reload режимов) |
| `API_KEY_HEADER` | имя заголовка ключа (по умолч. `X-API-Key`) |
| `RATE_LIMIT_*` | лимиты по ключу/пользователю/IP |
| `TASK_*` | таймауты и ретраи генерации |

### 2.4 Прод-обвязка (обязательно)
- HTTPS на GEN (reverse-proxy nginx/traefik + cert). Наружу — только `:443`.
- Файрвол: `:8000` доступен только с IP SRC (или весь трафик через прокси).
- `STORAGE_PROVIDER=r2` (бесплатный исходящий трафик) или S3.
- PostgreSQL — managed или с бэкапами; Redis — отдельно.
- Воркер на GPU-ноде; API можно на дешёвом CPU-узле (см. DEPLOYMENT.md/K8s).
- Сузить CORS (в проде GEN фронт к нему не ходит — можно вообще запретить).

---

## 3. Безопасность взаимодействия SRC ↔ GEN (критично)

1. **API-ключ** `X-API-Key` в каждом запросе SRC→GEN. Хранится только на SRC.
2. **HMAC-подпись callback** GEN→SRC. SRC ОБЯЗАН проверять:
   ```
   expected = HMAC_SHA256(WEBHOOK_SIGNING_SECRET, f"{ts}." + raw_body)
   compare_digest(expected, X-Webhook-Signature)   # ts = X-Webhook-Timestamp
   ```
   Без проверки кто угодно подделает «completed».
3. **TLS** на обоих направлениях. Никакого http в проде.
4. **IP allowlist**: GEN принимает SRC-трафик только с известных IP.
5. **Идемпотентность**: `request_id` (твой id) — повтор не создаёт вторую задачу.
6. **Не доверять клиенту**: цену/право на генерацию решает SRC, не фронт.
7. **Свежесть callback**: проверяй, что `X-Webhook-Timestamp` не старше ~5 мин
   (защита от replay).

---

## 4. Полный контракт API (GEN)

Базовый URL: `https://gen.example.com`. Заголовок: `X-API-Key: <ключ>`.

### 4.1 POST /uploads — загрузка фото (binary)
`multipart/form-data`, поле `file` (jpeg/png/webp, ≤25 МБ).
```
→ 200 {"image_url":"https://.../files/uploads/<id>.webp","size":15062,"content_type":"image/webp"}
→ 422 неподдерживаемый тип/пустой/слишком большой
```
> Альтернатива: SRC сам кладёт фото в своё хранилище и передаёт готовый URL —
> тогда /uploads не нужен.

### 4.2 POST /generate — создать задачу
```json
{
  "task_type": "photo",                  // "photo" | "video"
  "mode": "PHOTO_MODE_1",
  "image_url": "https://.../in.jpg",      // основной референс (лицо)
  "reference_urls": ["https://.../b.jpg"],// доп. персонажи/ракурсы, ≤8 (опц.)
  "driving_url": "https://.../move.mp4",  // управляющее видео/поза для движений (опц.)
  "user_id": "u_123",                     // опц.
  "request_id": "src-uuid",               // ИДЕМПОТЕНТНОСТЬ (рекоменд.)
  "callback_url": "https://src/api/cb",   // опц., иначе из API-ключа
  "metadata": {"any":"data"}              // вернётся в callback и доступно в промте
}
→ 202 {"status":"accepted","task_id":"..."}
→ 401 нет/невалидный ключ | 404 нет режима | 422 валидация | 429 rate limit
```

### 4.3 GET /tasks/{task_id} — статус (поллинг)
```json
{"task_id":"...","task_type":"photo","mode":"PHOTO_MODE_1",
 "status":"completed",            // queued|processing|completed|failed
 "progress":100,"result_url":"https://.../out.png",
 "error":null,"generation_time":8421,"metadata":{...}}
```

### 4.4 Прочее
- `GET /modes?task_type=photo` — список режимов.
- `POST /modes/{id}/preview` — отрендерить промт без генерации (для авторов).
- `POST /admin/modes/reload` — перечитать режимы (заголовок `Authorization: Bearer <internal-JWT>`).
- `GET /health`, `GET /ready`, `GET /metrics`.

### 4.5 Callback (GEN → SRC)
`POST <callback_url>`, заголовки `X-Webhook-Timestamp`, `X-Webhook-Signature`.
```json
// успех
{"task_id":"...","status":"completed","result_url":"...","generation_time":8421,"metadata":{...}}
// ошибка
{"task_id":"...","status":"failed","error":"...","metadata":{...}}
```

---

## 5. Поток запроса с другого сервера (SRC)

```
1. Пользователь на фронте: выбрал режим, прикрепил фото.
2. Фронт → SRC (со своей авторизацией).
3. SRC: проверка прав/баланса (если платно — резерв средств).
4. SRC → GEN: POST /uploads (или свой URL фото) → image_url.
5. SRC → GEN: POST /generate {mode, image_url, reference_urls?, driving_url?,
              request_id=<свой id>, callback_url, metadata:{src_id}}.
6. GEN → SRC: 202 {task_id}. SRC сохраняет task_id ↔ пользователь.
7. GEN обрабатывает (очередь → ComfyUI) и шлёт callback на SRC.
8. SRC: проверяет HMAC → completed: отдать результат пользователю (и списать
   средства); failed: вернуть резерв и показать ошибку.
9. Фронт получает результат от SRC (WebSocket/SSE или поллинг SRC).
```
Поллинг как фолбэк, если callback не дошёл: SRC раз в ~2 с дёргает `GET /tasks/{id}`.

Минимальные примеры кода фронта и SRC-бэка (с проверкой HMAC и логикой
резерв→списание→возврат) — в [INTEGRATION.md](INTEGRATION.md).

---

## 6. ПРОМТИНГ: где что менять и как переформировать

### 6.1 Карта файлов (что правишь)
```
config/
  models.yaml                  # модели за логическими именами (checkpoint, steps, cfg…)
  modes/photo/PHOTO_MODE_*.yaml    # 5 фото-режимов   ← промты тут
  modes/video/VIDEO_VARIATION_*.yaml  # 40 видео-режимов ← промты тут
  workflows/*.json             # ComfyUI-графы (логика сохранения лица/анимации)
```

### 6.2 Анатомия режима (единственный файл для промтинга)
```yaml
id: PHOTO_MODE_1
type: photo                 # photo | video
enabled: true               # вкл/выкл режим
model: photo_face_model     # ключ из models.yaml
workflow: photo_instantid   # файл config/workflows/photo_instantid.json
params:                     # параметры генерации (идут в workflow как {{param.X}})
  width: 1024
  height: 1024
  steps: 30
  seed: 0
preserve_face: true
reference_strength: 0.8
prompt_template: |          # ← ПОЗИТИВНЫЙ ПРОМТ (Jinja2)
  ...
negative_prompt: |          # ← НЕГАТИВНЫЙ ПРОМТ
  ...
```

### 6.3 Переменные в шаблоне промта (Jinja2)
`{{ image_url }}`, `{{ user_id }}`, `{{ request_id }}`, `{{ task_type }}`,
`{{ mode }}`, `{{ metadata.<любой_ключ> }}`.
Пример: `"portrait of {{ metadata.subject }}, {{ metadata.style }} style"`.
Если переменной нет — режим вернёт понятную ошибку (на preview/постановке).

### 6.4 Плейсхолдеры в workflow (config/workflows/*.json)
`{{prompt}}`, `{{negative}}`, `{{image_url}}`, `{{reference_0}}…`,
`{{reference_count}}`, `{{driving_url}}`, `{{seed}}`, `{{reference_strength}}`,
`{{param.<key>}}`, `{{model.name}}`. Подставляются перед отправкой в ComfyUI.

### 6.5 Цикл «переформирования» промта (без рестарта, без GPU для проверки)
```bash
# 1) изменил prompt_template/params в YAML
# 2) проверил рендер БЕЗ генерации:
curl -X POST https://gen/modes/PHOTO_MODE_1/preview -H "X-API-Key: KEY" \
     -H "Content-Type: application/json" -d '{"metadata":{"subject":"woman"}}'
#    → вернёт итоговый prompt/negative или 422 при ошибке шаблона
# 3) применил на лету:
TOKEN=$(docker compose exec -T api python -m scripts.mint_internal_token --subject ops)
curl -X POST https://gen/admin/modes/reload -H "Authorization: Bearer $TOKEN"
```
Добавить новый режим = положить новый YAML и сделать reload (ядро не трогаем).

---

## 7. Как добиться МАКСИМАЛЬНОГО качества

Качество = (правильный workflow) × (правильная модель) × (хороший промт) ×
(достаточный GPU). Промт сам по себе не спасёт плохой workflow и наоборот.

### 7.1 Сохранение лица (фото) — рецепт
> 📌 Готовый **детальный пример промта** с упором на сохранение лица и той же
> локации (полный режим-файл + параметры + рычаги) — в
> [PROMPTING.md → «Пример: МАКСИМАЛЬНОЕ сохранение лица + та же локация»](PROMPTING.md).

- **Модель/метод (в workflow):**
  - **PuLID** (Flux) или **InstantID** (SDXL) — лучшая узнаваемость по 1 фото.
  - Для «то же лицо 1:1» — **ReActor/inswapper** (face-swap поверх генерации).
  - Финишер: **FaceDetailer** (ADetailer) + апскейл (4x-UltraSharp) — резкость черт.
- **reference_strength:** 0.6–0.9. Выше → ближе к исходному лицу, но меньше
  стилистической свободы; ниже → красивее, но «уплывает» личность. Старт 0.8.
- **params:** SDXL `steps 30–40, cfg 4–6`; Flux `steps 28–32, cfg 3–4`.
  Разрешение портрета 768–1024; затем апскейл 1.5–2×.
- **Промт:** структура «субъект → одежда/сцена → свет → камера → качество».
  Пример позитива:
  ```
  professional studio portrait of the same person from reference,
  natural skin texture, sharp eyes, soft rim light, 85mm lens, shallow depth of field
  ```
  Негатив:
  ```
  deformed face, asymmetric eyes, extra fingers, plastic skin, lowres, blurry,
  watermark, text, duplicate face
  ```
- **Композиция/поза:** при необходимости ControlNet (OpenPose/Depth) в workflow.

### 7.2 Анимация персонажа (видео) — рецепт
- **Базовые i2v-модели:** Wan 2.2 i2v, CogVideoX, Hunyuan Video, LTX-Video.
- **Лицевая анимация:** **LivePortrait** (мимика/повороты с driving-видео,
  личность сохраняется) — даёт `driving_url`.
- **Движения тела:** AnimateAnyone / MimicMotion / Champ (по позе из `driving_url`).
- **Борьба с дрейфом лица (главная проблема видео):**
  - пофреймовый face-restore (GFPGAN/CodeFormer) в конце workflow;
  - короче клипы (2–5 с), фиксированный `seed`, умеренный fps (12–16);
  - face-conditioning от исходного фото на каждом шаге, если модель умеет.
- **params:** `num_frames 48–96, fps 12–16`; больше кадров = дольше и риск дрейфа.
- **GPU:** A100/H100 для приличного качества (видео ≈ 30× фото по времени).

### 7.3 Мульти-персонаж / добавление других персонажей — рецепт и пределы
- Передавай личности через `reference_urls` (до 8), в workflow — несколько
  InstantID/IP-Adapter веток или **региональный** conditioning (маски по зонам),
  либо инпейнт по очереди (по одному персонажу в свою область).
- Реалистично: 2 персонажа на фото — выполнимо с потерями; в видео несколько
  сохранённых личностей одновременно — **нестабильно** (фронтир). Управляй
  ожиданиями: для сложных сцен — компоновать по частям (инпейнт/сегментация).

### 7.4 Общие правила промта (качество)
- Конкретика бьёт длину: 1 чёткая сцена лучше «простыни» тегов.
- Веса важных токенов: `(keyword:1.2)`; не злоупотреблять (>1.4 ломает).
- Всегда заполнять **негатив** — он убирает артефакты лица/рук.
- Фиксируй `seed` для воспроизводимости; меняй сид для вариаций.
- Тестируй через `/preview` (промт) и серию из 3–4 сидов (визуал) до релиза режима.
- Параметры держи в `params`, текст — в `prompt_template`; не хардкодь в код.

### 7.5 Где включить апскейл/детейлер/ControlNet
Всё это — **узлы в ComfyUI workflow** (`config/workflows/*.json`), а не код.
Один раз собрал граф в ComfyUI → экспорт «Save (API Format)» → положил в файл →
указал `workflow: <имя>` в режиме. Параметры узлов можно вывести на плейсхолдеры
(`{{param.upscale}}` и т.п.) и менять из YAML.

---

## 8. Эксплуатация и масштаб (кратко)
- Очереди раздельные: `generation` (фото) и `generation_video` (видео) — видео не
  блокирует фото.
- Автоскейл воркеров — KEDA по длине очереди (k8s/keda-scaledobject.yaml).
- Задержка пользователю = ожидание в очереди + время генерации; API-оверхед ~12 мс.
  Когда очередь «взрывается» и сколько GPU надо — см. [CAPACITY.md](CAPACITY.md).
- Мониторинг: `/metrics` (Prometheus) + Grafana-дашборд; GPU — dcgm-exporter.

---

## 9. Чек-лист подключения нового сайта
1. На GEN: выпустить API-ключ `create_api_key "Site" --callback https://src/api/gen-callback`.
2. На SRC: сохранить `GEN_URL`, `GEN_API_KEY`, общий `WEBHOOK_SIGNING_SECRET`.
3. На SRC: эндпоинты `POST /api/generate`, `GET /api/generations/{id}`,
   `POST /api/gen-callback` (с проверкой HMAC); авторизация/баланс/оплаты.
4. Фронт ходит только на SRC.
5. Прогнать сценарий: upload → generate → callback (на mock-провайдере, без GPU).
6. Подключить GPU/ComfyUI, собрать workflow под плейсхолдеры, настроить режимы.
7. Прогнать качество: серия сидов, подбор `reference_strength`/`steps`/негатива.

---

## 10. Критерии приёмки
- [ ] GEN развёрнут, `GET /health` = ok, доступ к `:8000` только с SRC/прокси.
- [ ] HTTPS на SRC и GEN; CORS на GEN закрыт/сужен.
- [ ] SRC шлёт `X-API-Key`, проверяет HMAC callback и timestamp-свежесть.
- [ ] `request_id` обеспечивает идемпотентность (повтор не плодит задачи).
- [ ] Полный цикл upload→generate→callback работает (сначала на mock).
- [ ] Режимы редактируются через YAML + `/preview` + `/admin/modes/reload` без рестарта.
- [ ] (Прод) ComfyUI-workflow дают требуемое качество лица/видео на целевом GPU.
- [ ] Очереди фото/видео раздельны; настроены лимиты, метрики, алерты.
- [ ] Хранилище — R2/S3; файлы отдаются по публичному URL/CDN.
- [ ] (Прод) `SAFETY_PROVIDER=insightface`, `SAFETY_MIN_AGE=21` — проверка 21+ включена.
- [ ] При любой ошибке (вкл. блок 21+) на SRC уходит failed-callback, и SRC делает
      идемпотентный возврат средств пользователю.
- [ ] Скорость: применены turbo-LoRA/малые шаги/тёплый GPU (см. OPTIMIZATION.md).
