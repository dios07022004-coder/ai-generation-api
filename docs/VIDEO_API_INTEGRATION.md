# ТЗ: Видео-генерация — 40 режимов + интеграция API

Документ описывает, как устроены **40 видео-режимов**, как подключить их с любого сайта/сервера,
и как **менять модели и режимы без программирования**.

---

## 1. Архитектура (коротко)

```
Сайт/сервер-источник
   │  1) POST /uploads  (файл) → image_url
   │  2) POST /generate (mode + image_url) → task_id
   ▼
API (FastAPI)  → проверка ключа, 21+/safety, лимиты → задача в очередь (Redis), фиксация оплаты
   ▼
Worker (Celery) → грузит входы в ComfyUI → подставляет их в workflow режима → ComfyUI (GPU)
   ▼
Worker → сохраняет результат → статус completed/ failed → CALLBACK на сервер-источник (HMAC)
   ▼
Источник: показывает видео / возвращает деньги при ошибке
```

**Декларативность:** режим = YAML-файл. Контент-менеджер правит ТОЛЬКО промт/параметры.
Код не трогается. Модель меняется в одном файле.

```
config/
  models.yaml                 # логические модели → файлы/параметры
  modes/video/VIDEO_VARIATION_1..40.yaml   # 40 режимов (промт+параметры)
  workflows/video_i2v.json    # ComfyUI-граф (Wan 2.2 i2v) — общий для всех 40
```

---

## 2. 40 видео-режимов

Все режимы — **image-to-video**: оживляют присланное фото, **сохраняя лицо/идентичность/локацию**,
и применяют своё движение. ID: `VIDEO_VARIATION_1 … VIDEO_VARIATION_40`.

| # | ID | Что делает |
|---|---|---|
| 1–10 | VIDEO_VARIATION_1..10 | **Камера:** zoom in/out, орбита влево/вправо, dolly in/out, пан влево/вправо, кран вверх/вниз |
| 11–24 | VIDEO_VARIATION_11..24 | **Действия:** повернуться к камере, идти вперёд, махнуть рукой, кивнуть, улыбнуться, осмотреться, сесть, встать, развернуться, тряхнуть волосами, шаг назад, наклон к камере, скрестить руки, послать поцелуй |
| 25–30 | VIDEO_VARIATION_25..30 | **Идл/тонкое:** дыхание+моргание, волосы на ветру, одежда на ветру, медленный взгляд, лёгкое покачивание, глубокий вдох |
| 31–36 | VIDEO_VARIATION_31..36 | **Кинематограф:** slow-mo, драматичный зум, мечтательный софт-фокус, винтаж-плёнка, золотой час, реалистичная «ручная» камера |
| 37–40 | VIDEO_VARIATION_37..40 | **Окружение:** дождь, снег, листопад, рябь воды |

Каждый режим — 5 сек (81 кадр @ 16 fps), 480×832, 8 шагов (lightning), cfg 1.0.
**Полный список движений** — в самих YAML-файлах (`config/modes/video/`).

---

## 3. API: эндпоинты

Базовый URL (тест): `http://<SERVER_IP>:8000`. Везде заголовок **`X-API-Key: <ключ>`**.

### 3.1 Загрузка фото
```
POST /uploads          (multipart/form-data; field "file"; jpg/png/webp, ≤25 МБ)
→ 200 { "image_url": "...", "size": 12345, "content_type": "image/jpeg" }
```

### 3.2 Постановка задачи
```
POST /generate         (application/json)
{
  "task_type": "video",
  "mode": "VIDEO_VARIATION_13",        // один из 40
  "image_url": "https://.../in.jpg",   // из /uploads
  "user_id": "u_123",                  // ваш ID пользователя (для лимитов/оплаты)
  "request_id": "req_abc",             // ваш ID запроса (идемпотентность/возврат)
  "callback_url": "https://your.site/cb",  // опц.: куда прислать результат
  "metadata": { "change": "..." }      // опц.: доп. текст в промт ({{metadata.change}})
}
→ 202 { "status": "accepted", "task_id": "..." }
```
Доп. поля (опц.): `reference_urls[]` (доп. персонажи/ракурсы), `driving_url` (видео-поза для переноса движения), `mask_url` (маска правки).

### 3.3 Статус задачи (поллинг)
```
GET /tasks/{task_id}
→ 200 {
  "task_id","request_id","task_type","mode",
  "status": "queued|processing|completed|failed",
  "progress": 0..100,
  "result_url": "https://.../out.mp4",   // когда completed
  "error": "...",                        // когда failed
  "generation_time": 123000,             // мс
  "metadata": {...}, "created_at","updated_at"
}
```

### 3.4 Список режимов (для выпадающего списка на сайте)
```
GET /modes?task_type=video
→ 200 { "count": 40, "modes": [ {"id","type","enabled","model"}, ... ] }
```

### 3.5 Предпросмотр промта (без генерации, не тратит GPU)
```
POST /modes/{mode_id}/preview   { "image_url": "...", "metadata": {...} }
→ 200 { "prompt": "...", "negative_prompt": "...", "params": {...} }
```

### 3.6 Горячая перезагрузка режимов/моделей (без рестарта)
```
POST /admin/modes/reload        (заголовок: internal JWT)
→ 200 { "status": "reloaded", "count": N }
```

---

## 4. Callback на сервер-источник (результат)

Когда задача завершена, API сам шлёт POST на `callback_url` (или глобальный из настроек),
**подписанный HMAC** (заголовок подписи проверяйте секретом).

Успех:
```json
{ "task_id":"...", "status":"completed", "result_url":"https://.../out.mp4",
  "generation_time": 123000, "metadata": {...} }
```
Ошибка (← здесь источник возвращает деньги):
```json
{ "task_id":"...", "status":"failed", "error":"<причина>", "metadata": {...} }
```

**Оплата/возврат:** списываете при `accepted`; при callback `failed` (или статусе `failed` в поллинге) —
делаете возврат на стороне источника по `request_id`/`user_id`.

---

## 5. Как менять РЕЖИМЫ (без кода)

1. Открыть `config/modes/video/VIDEO_VARIATION_N.yaml`.
2. Менять **только** `prompt_template`, `negative_prompt`, `params` (steps/cfg/num_frames/размер).
   - ⚠️ Не удалять якоря «keep the SAME face/identity/location» — иначе лицо/сцена «уплывут».
3. Применить без рестарта: `POST /admin/modes/reload` (или перезапустить worker).
4. Проверить итоговый промт: `POST /modes/{id}/preview`.

Добавить новый режим = просто новый YAML-файл в этой папке (он сразу появится в `/modes`).

---

## 6. Как менять МОДЕЛИ (Q: «возможно буду менять модели»)

**Да, это просто — модель меняется в одном месте.**

`config/models.yaml`:
```yaml
video_generation_model:
  name: wan2.2_i2v_14B   # логическое имя; реальные файлы — в workflow
  type: video
  steps: 8
  cfg: 1.0
  fps: 16
```

Два сценария:

**A. Та же архитектура** (другой чекпойнт Wan / другая версия с теми же нодами):
1. Скачать файл модели в ComfyUI (`models/...`).
2. Поправить `name`/`steps`/`cfg` в `models.yaml`.
3. `POST /admin/modes/reload`.
→ Всё. Код и режимы не трогаются. Все 40 режимов сразу на новой модели.

**B. Другая архитектура** (другой движок: LTX / CogVideoX / иная схема нод):
1. Собрать граф в ComfyUI → «Save (API Format)» → положить как `config/workflows/<new>.json` (с плейсхолдерами).
2. В режимах указать `workflow: <new>` (или поменять у общего).
3. `reload`.
→ Один новый файл workflow. Кода по-прежнему нет.

**Плейсхолдеры в workflow:** `{{image_name}}` (фото), `{{reference_0_name}}`, `{{driving_url}}`,
`{{prompt}}`, `{{negative}}`, `{{seed}}`, `{{param.num_frames}}`, `{{param.fps}}`, `{{param.steps}}`,
`{{param.cfg}}`, `{{param.width}}`, `{{param.height}}`, `{{model.name}}`.

---

## 7. Единственный недостающий шаг: привязать Wan 2.2 workflow

Сейчас `config/workflows/video_i2v.json` — **заглушка**. Чтобы 40 режимов заработали:
1. На новом 4090-сервере поднять ComfyUI, собрать/открыть рабочий **Wan 2.2 i2v** граф (как мы тестировали).
2. Settings → Enable Dev mode → **Save (API Format)** → прислать JSON.
3. Я вставлю его в `video_i2v.json` с плейсхолдерами из §6 → все 40 режимов оживут через API.

---

## 8. Безопасность (обязательно для adult-платформы)

- **21+ / верификация возраста** перед генерацией (провайдер safety; включить в `.env`).
- **Согласие**; **запрет** загрузки лиц реальных людей в сексуальный контент (anti-NCII).
- Логирование/учёт обращений.

---

## 8b. Партнёрский биллинг (оплата за генерацию)

Каждый **API-ключ = партнёр** с предоплатным балансом в кредитах (**1 кредит = 1 ₽**).
За каждую генерацию списывается цена режима; при нуле — отказ **402**; при сбое генерации —
**автовозврат**. Включается флагом `BILLING_ENABLED=true` (по умолчанию выкл — поведение прежнее).

**Цена** — в `config/pricing.yaml` (только целые кредиты), по умолчанию **видео 40**. Приоритет:
`ApiKey.price_overrides` → `api_keys` в yaml → `modes` в yaml → `defaults` в yaml. Нет цены → отказ (fail-closed).

**Жизненный цикл оплаты:** `/generate` → резерв (списание) → успех: списание остаётся (+аудит-строка) ·
терминальный сбой: возврат. Идемпотентно (повтор `request_id` не списывает дважды; возврат ровно один).

**Пополнение баланса партнёра (вручную, после оплаты тебе):**
```
python -m scripts.topup <api_key_id> <amount_credits> [--note "оплата за июнь"]
```
или админ-эндпоинтом (internal JWT):
```
POST /admin/billing/{api_key_id}/topup   { "amount_credits": 400, "note": "..." }
GET  /admin/billing/{api_key_id}          → баланс + последние движения + сводка
```

**Партнёр видит своё** (по `X-API-Key`):
```
GET /billing/balance               → { "balance_credits": 360 }
GET /billing/usage?from=&to=       → { summary: {...}, entries: [...] }
```

**Что увидит партнёр при нехватке средств:** `POST /generate` → `402 { error.code: "insufficient_balance" }`.
Пополни баланс — и запросы снова проходят.

## 9. Чек-лист подключения сайта
1. Получить `X-API-Key`.
2. `GET /modes?task_type=video` → показать 40 режимов в UI.
3. Юзер прикрепил фото → `POST /uploads` → `image_url`.
4. `POST /generate` (mode + image_url + user_id + request_id [+ callback_url]).
5. Поллить `GET /tasks/{id}` ИЛИ принять callback.
6. `completed` → показать `result_url`; `failed` → вернуть деньги.
