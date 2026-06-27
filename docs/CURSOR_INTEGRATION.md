# Промт для Cursor: подключить сайт к API генерации

> Скопируй ВЕСЬ текст ниже в Cursor (в проекте твоего САЙТА, не в этом API).
> Внизу — блок **[ЗАДАЧА]**, допиши детали своего проекта.

---

Ты интегрируешь мой веб-сервис с внешним **API генерации фото/видео**. Этот API —
отдельный сервис (на GPU-сервере). Мой сайт (этот проект) — «сервер-источник»:
у него свои пользователи, баланс и оплаты; он вызывает API генерации и показывает
результат. **Фронтенд НИКОГДА не ходит в API генерации напрямую и не знает его
ключ — только через мой бэкенд.**

## Данные API генерации (вынеси в переменные окружения, не в код)
```
GEN_URL=https://<домен-или-IP-gpu-сервера>      # напр. http://45.80.129.30:8000
GEN_API_KEY=sk_...                               # ключ моего сервиса в API генерации
WEBHOOK_SECRET=...                               # = WEBHOOK_SIGNING_SECRET API генерации (для проверки подписи)
```

## Контракт API генерации (что я вызываю)
- `POST {GEN_URL}/uploads` — загрузка фото. multipart, поле `file` (jpeg/png/webp ≤25MB),
  заголовок `X-API-Key: {GEN_API_KEY}`. Ответ: `{"image_url": "...", ...}`.
- `POST {GEN_URL}/generate` (заголовок `X-API-Key`), тело:
  ```json
  {
    "task_type": "photo",            // "photo" | "video"
    "mode": "PHOTO_MODE_1",          // id режима (фото) / "VIDEO_VARIATION_7" (видео)
    "image_url": "https://...",      // из /uploads (или мой публичный URL)
    "mask_url": "https://...",       // опц. — для редактирования (inpaint)
    "reference_urls": ["https://..."],// опц. — доп. персонажи
    "user_id": "<id моего юзера>",
    "request_id": "<МОЙ уникальный id операции>",   // идемпотентность!
    "callback_url": "{MY_URL}/api/gen-callback",
    "metadata": { "generation_id": "<мой id>", "instruction": "..." }
  }
  ```
  Ответ: `202 {"status":"accepted","task_id":"..."}`.
- `GET {GEN_URL}/tasks/{task_id}` (заголовок `X-API-Key`) — статус (фолбэк-поллинг):
  `{"status":"queued|processing|completed|failed","result_url":"...","error":"..."}`.
- **Callback** (API генерации сам шлёт мне на `callback_url`) с заголовками
  `X-Webhook-Timestamp`, `X-Webhook-Signature` = `hmac_sha256(WEBHOOK_SECRET, "{ts}." + raw_body)`.
  Тело: `{"task_id","status":"completed|failed","result_url","error","generation_time","metadata"}`.

## Что нужно реализовать НА МОЁМ сайте
1. **Эндпоинт `POST /api/generate`** (для фронта, с моей авторизацией):
   - проверить, что пользователь залогинен;
   - посчитать цену по СВОЕМУ прайсу (фото 60 ₽, видео 120–130 ₽) — НЕ доверять клиенту;
   - **зарезервировать средства** (hold) на балансе; если не хватает → `402`;
   - загрузить фото в API генерации (`/uploads`) → `image_url`;
   - создать у себя запись `generation` (status=pending) с моим `generation_id`;
   - вызвать `{GEN_URL}/generate` с `request_id=<generation_id>`, `callback_url`, `metadata`;
   - вернуть фронту `{generation_id}`.
2. **Эндпоинт `GET /api/generations/{id}`** — статус для фронта (из моей БД).
3. **Эндпоинт `POST /api/gen-callback`** — приём результата:
   - **ОБЯЗАТЕЛЬНО проверить HMAC-подпись** (иначе кто угодно подделает «оплачено»);
   - проверить свежесть `X-Webhook-Timestamp` (не старше ~5 мин);
   - идемпотентность: если по этому `generation_id` уже списано/возвращено — выйти;
   - `completed` → списать резерв (charge), сохранить `result_url`, уведомить юзера;
   - `failed` → **вернуть резерв (refund)**, показать ошибку.
4. Фронт: загрузка файла + выбор режима → `POST /api/generate` → поллинг
   `GET /api/generations/{id}` (или WebSocket) → показать результат.

## Проверка HMAC-подписи callback
Node.js:
```js
const crypto = require("crypto");
function verify(rawBody, ts, sig) {
  const exp = crypto.createHmac("sha256", process.env.WEBHOOK_SECRET)
    .update(Buffer.concat([Buffer.from(ts + "."), rawBody])).digest("hex");
  return crypto.timingSafeEqual(Buffer.from(exp), Buffer.from(sig));
}
// ВАЖНО: брать СЫРОЕ тело запроса (raw body), а не распарсенный JSON.
```
Python:
```python
import hmac, hashlib
def verify(raw: bytes, ts: str, sig: str) -> bool:
    exp = hmac.new(WEBHOOK_SECRET.encode(), f"{ts}.".encode()+raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(exp, sig)
```

## Таблицы на моей стороне (минимум)
```
users(id, ..., balance_kopecks)
transactions(id, user_id, kind, amount_kopecks, status, ext_id)   -- topup|hold|charge|refund
generations(id, user_id, task_id, type, mode, price_kopecks, status, result_url, refunded bool, charged bool)
```
Деньги — в копейках (целое). Резерв→списание при completed→возврат при failed.

## Правила (обязательны)
- Фронт ходит ТОЛЬКО на мой бэкенд; `GEN_API_KEY` и `WEBHOOK_SECRET` — только на бэкенде.
- Цену считает бэкенд по своему прайсу.
- `request_id` = мой `generation_id` (идемпотентность — повтор не плодит задачи/списания).
- Возврат денег строго один раз (флаг `refunded`).
- Результат лучше перезалить в моё хранилище (ссылка API генерации может протухнуть).
- Все вызовы — по HTTPS.

---

## [ЗАДАЧА]
<!-- Опиши свой проект и что сделать. Например:
- Стек моего сайта: (Next.js + Node / Laravel / Django ...).
- Где у меня авторизация и таблица пользователей.
- Платёжный провайдер (YooKassa/Stripe) для пополнения баланса.
- Какие режимы показывать на фронте (список PHOTO_MODE_*/VIDEO_VARIATION_*).
- Реализуй: /api/generate, /api/generations/{id}, /api/gen-callback (с проверкой HMAC),
  баланс/резерв/списание/возврат, и UI загрузки фото + выбора режима + показа результата.
-->

(сюда — детали твоего сайта и задача)
