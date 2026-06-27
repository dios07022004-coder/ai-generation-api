# Интеграция: фронтенд → бэкенд → генерация, с аккаунтами и оплатами

Документ показывает, как подключить **любой сервис** к этому API генерации:
авторизация пользователей, оплаты (фото 60 ₽, видео 120–130 ₽), полный поток
от кнопки на фронте до результата.

---

## 1. Кто за что отвечает (важно понять сразу)

```
[ Фронтенд ]      [ ТВОЙ бэкенд = «сервис-источник» ]        [ ЭТОТ API генерации ]
   браузер   ──▶   аккаунты, баланс, ОПЛАТЫ, бизнес-логика  ──▶  только генерация
                   (хранит пользователей и деньги)               (API-ключи сервисов)
                          ▲                                              │
                          └───────────── callback (результат) ──────────┘
```

- **Этот API** — движок генерации. Он НЕ знает про конечных пользователей и
  деньги. Он аутентифицирует **сервисы** по API-ключу (`X-API-Key`).
- **Твой бэкенд (сервис-источник)** — владелец пользователей, балансов и оплат.
  Он списывает 60/120 ₽, дёргает этот API и отдаёт результат пользователю.

Почему так: один и тот же движок может обслуживать несколько сайтов/ботов, у
каждого своя авторизация и биллинг. Движок остаётся простым и переиспользуемым.

> Если нужен централизованный биллинг внутри самого движка — это отдельный
> модуль (таблицы users/api_keys уже есть); но рекомендуемый и масштабируемый
> путь — биллинг на стороне сервиса.

---

## 2. Полный поток (с оплатой)

```
1. Пользователь логинится на твоём сайте (твоя авторизация: JWT/сессия).
2. Выбирает режим (PHOTO_MODE_x / VIDEO_VARIATION_x) и прикрепляет фото.
3. Фронт → твой бэкенд: "хочу генерацию, режим X, вот файл".
4. Твой бэкенд:
   a. проверяет баланс пользователя (или инициирует оплату);
   b. РЕЗЕРВИРУЕТ сумму (hold): фото 60 ₽ / видео 120–130 ₽;
   c. загружает фото в API: POST /uploads → image_url;
   d. POST /generate (X-API-Key, callback_url, request_id, metadata);
   e. сохраняет task_id ↔ user_id ↔ payment_id.
5. API генерации обрабатывает и шлёт callback на твой бэкенд.
6. Твой бэкенд (проверив HMAC-подпись):
   - completed → СПИСЫВАЕТ резерв, сохраняет результат, уведомляет юзера;
   - failed    → ВОЗВРАЩАЕТ резерв (рефанд), показывает ошибку.
7. Фронт показывает результат (через WebSocket/SSE или поллинг твоего бэкенда).
```

Главное правило денег: **резерв до генерации, списание после успеха, возврат
при ошибке**. Цену считает ТОЛЬКО бэкенд (клиенту не верим).

---

## 3. Цены

Держи прайс на своём бэкенде (не на клиенте):

```python
PRICES_RUB = {
    "photo": 60,
    "video": 125,   # 120–130 — можно за вариацию (см. ниже)
}
# при желании — цена за конкретную вариацию:
VIDEO_PRICE_OVERRIDE = {"VIDEO_VARIATION_7": 130, "VIDEO_VARIATION_12": 120}

def price_of(task_type: str, mode: str) -> int:
    if task_type == "video":
        return VIDEO_PRICE_OVERRIDE.get(mode, PRICES_RUB["video"])
    return PRICES_RUB["photo"]
```

---

## 4. Модель оплаты: разовая vs баланс (кредиты)

| Модель | Плюсы | Минусы |
|---|---|---|
| **Предоплаченный баланс (рекомендую)** | мгновенный старт генерации, меньше платёжных round-trip, удобно для частых генераций | нужно «пополнить кошелёк» |
| Разовая оплата за каждую генерацию | проще для редких разовых заказов | платёжная пауза перед каждой генерацией |

**Рекомендация:** баланс/кредиты. Пользователь пополняет кошелёк (YooKassa/
Stripe), а каждая генерация просто списывает 60/125 ₽ с баланса — без ожидания
платёжного провайдера в момент генерации.

### Таблицы на твоём бэкенде (минимум)

```sql
users(id, email, password_hash, balance_kopecks, created_at)
transactions(id, user_id, kind, amount_kopecks, status, ext_payment_id, created_at)
            -- kind: topup | hold | charge | refund
generations(id, user_id, task_id, mode, task_type, price_kopecks, status, result_url)
```

Деньги храни в копейках (целое), не во float.

---

## 5. Платёжный провайдер (₽: YooKassa)

Пополнение баланса:

```
1. Фронт: "пополнить на 500 ₽" → твой бэкенд создаёт платёж в YooKassa.
2. YooKassa возвращает confirmation_url → редиректишь пользователя на оплату.
3. YooKassa шлёт webhook payment.succeeded → твой бэкенд:
   - проверяет подпись/идемпотентность,
   - increment users.balance_kopecks,
   - transactions(kind=topup, status=success).
```

Для Stripe (валюта) — та же логика: PaymentIntent + webhook `payment_intent.
succeeded`. Никогда не начисляй баланс по ответу фронта — только по webhook
провайдера.

---

## 6. Код: фронтенд (браузер)

```js
// 0) пользователь уже залогинен на твоём сайте: есть твой session/JWT.
// 1) загрузка фото и запрос генерации идут на ТВОЙ бэкенд (не напрямую в движок!)
async function generate(file, mode) {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("mode", mode);              // PHOTO_MODE_1 / VIDEO_VARIATION_7
  fd.append("task_type", "photo");

  const res = await fetch("/api/generate", {       // ТВОЙ бэкенд
    method: "POST",
    headers: { Authorization: `Bearer ${userToken}` },
    body: fd,
  });
  if (res.status === 402) throw new Error("Недостаточно средств — пополните баланс");
  const { generation_id } = await res.json();

  // 2) ждём результат: поллинг твоего бэкенда или WebSocket
  return poll(generation_id);
}

async function poll(id) {
  for (;;) {
    const r = await fetch(`/api/generations/${id}`, {
      headers: { Authorization: `Bearer ${userToken}` },
    }).then(r => r.json());
    if (r.status === "completed") return r.result_url;
    if (r.status === "failed") throw new Error(r.error);
    await new Promise(s => setTimeout(s, 1500));
  }
}
```

Фронт НИКОГДА не ходит в движок напрямую и не знает его API-ключ — только твой
бэкенд.

---

## 7. Код: твой бэкенд (сервис-источник)

Пример на Python/FastAPI (логика та же на любом стеке):

```python
GEN_API = "https://gen.example.com"
GEN_API_KEY = "sk_..."            # ключ ЭТОГО сервиса в движке (секрет)
WEBHOOK_SECRET = "..."            # = WEBHOOK_SIGNING_SECRET движка

@app.post("/api/generate")
async def create_generation(file: UploadFile, mode: str, task_type: str, user=Depends(auth)):
    price = price_of(task_type, mode) * 100          # в копейки
    # 1) проверка и РЕЗЕРВ средств (атомарно в транзакции БД)
    if not reserve_funds(user.id, price):
        raise HTTPException(402, "insufficient funds")

    # 2) загрузка фото в движок
    img = httpx.post(f"{GEN_API}/uploads",
                     headers={"X-API-Key": GEN_API_KEY},
                     files={"file": (file.filename, await file.read(), file.content_type)}
                     ).json()["image_url"]

    # 3) создаём генерацию (request_id = идемпотентность, metadata = наши id)
    gen = create_generation_row(user.id, mode, task_type, price)  # status=pending
    httpx.post(f"{GEN_API}/generate",
               headers={"X-API-Key": GEN_API_KEY},
               json={
                   "task_type": task_type, "mode": mode, "image_url": img,
                   "user_id": str(user.id),
                   "request_id": gen.id,                 # наш id → идемпотентность
                   "callback_url": f"{MY_URL}/api/gen-callback",
                   "metadata": {"generation_id": gen.id, "user_id": user.id},
               })
    return {"generation_id": gen.id}


@app.post("/api/gen-callback")
async def gen_callback(request: Request):
    body = await request.body()
    ts  = request.headers.get("X-Webhook-Timestamp", "")
    sig = request.headers.get("X-Webhook-Signature", "")
    # ОБЯЗАТЕЛЬНО проверяем подпись движка:
    expected = hmac.new(WEBHOOK_SECRET.encode(), f"{ts}.".encode() + body,
                        hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        raise HTTPException(401, "bad signature")

    data = json.loads(body)
    gen = get_generation(data["task_id"])             # мы храним task_id↔gen
    if data["status"] == "completed":
        finalize_charge(gen)                          # hold → charge
        save_result(gen, data["result_url"])          # лучше перезалить файл к себе
        notify_user(gen.user_id, gen.id)              # websocket/push
    else:
        refund(gen)                                   # возвращаем резерв
    return {"ok": True}
```

Проверка подписи на Node.js:

```js
const crypto = require("crypto");
function verify(rawBody, ts, sig) {
  const exp = crypto.createHmac("sha256", WEBHOOK_SECRET)
                    .update(Buffer.concat([Buffer.from(ts + "."), rawBody]))
                    .digest("hex");
  return crypto.timingSafeEqual(Buffer.from(exp), Buffer.from(sig));
}
```

---

## 8. Безопасность и устойчивость (обязательно)

- **Подпись callback** — всегда проверяй HMAC (раздел 7). Иначе кто угодно
  «подтвердит» генерацию и спишет/вернёт деньги.
- **Цену считает бэкенд** по своему прайсу; никогда не из тела запроса клиента.
- **Идемпотентность**: `request_id` = твой `generation_id`. Повторный вызов
  движка вернёт ту же задачу — не запустит вторую и не спишет дважды.
- **Резерв→списание→возврат**: деньги не списываем до успеха; при `failed` —
  рефанд. Защищает от «оплатил, но не сгенерилось».
- **Свой ключ движка** (`GEN_API_KEY`) держи только на бэкенде, не на фронте.
- **Перезаливай результат к себе** (или в своё хранилище) — не завязывайся на
  ссылку движка надолго (TTL/чистка).
- **Лимиты**: у движка есть rate-limit по ключу/пользователю; на своём бэкенде
  тоже ограничивай запуск генераций на пользователя.

---

## 8.1 Возврат средств при ошибке (рефанд) — ОБЯЗАТЕЛЬНО

Деньги живут на SRC, поэтому возврат делает **SRC по failed-callback** от движка.
Движок гарантирует доставку ошибки (HMAC-подпись, ретраи доставки).

Когда возвращать резерв/средства:
- callback `status: "failed"` (в т.ч. `content_blocked: age_check_failed` —
  заблокировано проверкой 21+; `provider_error`; таймаут и т.п.);
- задача не завершилась за разумный срок (фолбэк-поллинг `GET /tasks/{id}` →
  `failed`/завис → вернуть).

Правила:
- **Идемпотентность возврата**: рефанд по `generation_id` строго один раз
  (флаг в БД), чтобы повтор callback не вернул деньги дважды.
- **Списание — только при `completed`**; до этого средства в резерве (hold).
- Логируй причину (`error`) в `transactions`/`generations` для поддержки.

```python
def gen_callback(...):
    # ... проверка HMAC ...
    gen = get_generation(data["task_id"])
    if gen.refunded or gen.charged:          # идемпотентность
        return {"ok": True}
    if data["status"] == "completed":
        charge(gen)                          # hold → списание
        save_result(gen, data["result_url"])
    else:                                    # failed (вкл. блок 21+)
        refund(gen)                          # вернуть резерв на баланс юзера
        mark_failed(gen, data.get("error"))
    notify_user(gen.user_id, gen.id)
    return {"ok": True}
```

## 8.2 Безопасность контента (21+) — на стороне движка

Движок **до генерации** проверяет возраст лица на входном фото и блокирует
несовершеннолетних (анти-CSAM, `SAFETY_PROVIDER`). При блоке задача падает с
`content_blocked: age_check_failed`, и SRC получает failed-callback → делает
рефанд (см. 8.1). SRC может дополнительно показать пользователю причину.

## 9. Экономика (быстрая прикидка)

| Тип | Цена пользователю | Время GPU (≈) | Себестоимость GPU* |
|---|---|---|---|
| Фото | 60 ₽ | ~6 с (4090) | ~0.3–0.8 ₽ |
| Видео | 120–130 ₽ | ~3 мин (4090) | ~6–15 ₽ |

\* при аренде 4090 ~$0.5/час: секунда ≈ 0.013 ₽×время. Себестоимость генерации
много ниже цены — маржа высокая; основной риск — простой GPU (плати за аренду,
даже когда нет заказов). Детали нагрузки/масштаба — [CAPACITY.md](CAPACITY.md).

---

## 10. Чек-лист подключения нового сервиса

1. Выпусти сервису API-ключ движка: `python -m scripts.create_api_key "Имя" --callback https://сервис/api/gen-callback`.
2. Пропиши на бэкенде сервиса: `GEN_API`, `GEN_API_KEY`, `WEBHOOK_SECRET`.
3. Реализуй у себя: авторизацию, баланс, прайс, резерв/списание/возврат.
4. Эндпоинты у себя: `POST /api/generate`, `GET /api/generations/{id}`,
   `POST /api/gen-callback` (с проверкой HMAC).
5. Фронт ходит ТОЛЬКО на твой бэкенд.
6. Пополнение баланса — через YooKassa/Stripe webhook.
```
