# API Reference

Базовый URL: `http://<host>:8000`
Аутентификация: заголовок `X-API-Key: <raw key>` (имя настраивается `API_KEY_HEADER`).

---

## POST /generate

Принять задачу генерации.

**Body:**
```json
{
  "task_type": "photo",            // "photo" | "video"
  "mode": "PHOTO_MODE_1",          // id режима из config/modes
  "image_url": "https://...",      // основной референс (лицо/персонаж), опц.
  "reference_urls": ["https://..."],// доп. персонажи/ракурсы (мульти-персонаж), ≤8, опц.
  "driving_url": "https://...",    // управляющее видео/поза для движений, опц.
  "user_id": "u_123",              // опц.
  "request_id": "req_abc",         // опц., идемпотентность
  "callback_url": "https://...",   // опц., иначе берётся из API-ключа
  "metadata": {}                   // опц., прокидывается в промт и callback
}
```

`reference_urls` и `driving_url` доступны в ComfyUI-workflow как плейсхолдеры
`{{reference_0}}`, `{{reference_1}}`, … , `{{reference_count}}`, `{{driving_url}}`.

**202 Accepted:**
```json
{ "status": "accepted", "task_id": "..." }
```

Ошибки: `401` (ключ), `429` (rate limit), `404` (нет режима), `422` (валидация).

---

## POST /uploads

Загрузить исходное фото (binary, `multipart/form-data`, поле `file`).
Допустимы `image/jpeg|png|webp`, до 25 МБ. Возвращает `image_url` для `/generate`.

```bash
curl -X POST http://host/uploads -H "X-API-Key: <key>" -F "file=@photo.webp"
# → {"image_url":"https://.../files/uploads/<id>.webp","size":15062,"content_type":"image/webp"}
```

## GET /tasks/{task_id}

Статус задачи (только своей).

**200 OK:**
```json
{
  "task_id": "...", "task_type": "photo", "mode": "PHOTO_MODE_1",
  "status": "completed",           // queued | processing | completed | failed
  "progress": 100,
  "result_url": "https://.../abc.png",
  "error": null,
  "generation_time": 8421,         // ms
  "metadata": {}
}
```

---

## GET /modes?task_type=photo

Список доступных режимов.

```json
{ "count": 5, "modes": [{"id":"PHOTO_MODE_1","type":"photo","enabled":true,"model":"photo_face_model"}] }
```

## POST /modes/{mode_id}/preview

Отрендерить промт режима на тестовых данных **без генерации** (для авторов
промтов). Тело (всё опционально): `{ image_url, user_id, request_id, metadata }`.
```json
{ "mode":"PHOTO_MODE_1", "model":"photo_face_model", "workflow":"photo_instantid",
  "params":{...}, "prompt":"...", "negative_prompt":"..." }
```
Ошибка шаблона (несуществующая переменная) → `422`.

## POST /admin/modes/reload

Перечитать режимы/модели с диска без рестарта. **Требует internal JWT**
(не API-ключ): заголовок `Authorization: Bearer <token>`.
Токен выпускается `python -m scripts.mint_internal_token`.
Ответ: `{ "status": "reloaded", "count": 45 }`

---

## Callback (исходящий, на сервер-источник)

`POST <callback_url>` с заголовками:
```
X-Webhook-Timestamp: 1719300000
X-Webhook-Signature: <hex hmac_sha256(secret, "{ts}." + raw_body)>
```

Успех:
```json
{ "task_id":"...", "status":"completed", "result_url":"...", "generation_time":8421, "metadata":{} }
```
Ошибка:
```json
{ "task_id":"...", "status":"failed", "error":"...", "metadata":{} }
```

Проверка подписи на стороне источника (псевдокод):
```python
expected = hmac_sha256(secret, f"{ts}.".encode() + raw_body).hexdigest()
assert hmac.compare_digest(expected, header_signature)
```

---

## Системные

- `GET /health` — `{ "status": "ok", "provider": "mock" }`
- `GET /ready` — готовность + число загруженных режимов
- `GET /metrics` — метрики Prometheus
