# Полное руководство: как пользоваться (ТЗ эксплуатации)

Единый документ «как всем пользоваться» — от включения сервера до подключения сайта.
Код трогать не нужно: всё управляется конфигами и командами.

> Связанные документы:
> - [HOWTO_MODELS_AND_EDITING.md](HOWTO_MODELS_AND_EDITING.md) — подробно про смену моделей и правку промтов.
> - [VIDEO_API_INTEGRATION.md](VIDEO_API_INTEGRATION.md) — подробно про API и подключение сайта.

---

## 1. Что это такое

Самостоятельный сервис генерации **фото и видео по промтам** на своём GPU.
- Пользователь присылает фото + выбирает **режим** → сервис генерирует результат.
- **40 видео-режимов** и фото-режимы — заранее настроены; контент-менеджер правит только промты.
- Доступ снаружи — по **HTTP API** (твой сайт шлёт запросы).

Стек: **API (FastAPI)** + **очередь (Celery/Redis)** + **БД (Postgres)** + **ComfyUI (GPU)**.

---

## 2. Адреса и доступы

| Что | Адрес/значение |
|---|---|
| Сервер (IP) | `178.130.61.39` (меняется, если пересоздать сервер) |
| API | `http://178.130.61.39:8000` |
| Тест-страница | `http://178.130.61.39:8000/ui/test.html` |
| ComfyUI (сборка графов) | `http://178.130.61.39:8188` |
| Консоль сервера | Selectel → Серверы → videophotoAPI → **Консоль** (логин `root` + пароль) |
| API-ключ | заголовок `X-API-Key: sk_...` (создаётся командой, см. §9) |
| Проект на сервере | `/root/ai-generation-api` |
| ComfyUI на сервере | `/root/ComfyUI` |

---

## 3. Включение / выключение сервера (экономия денег)

GPU тарифицируется, пока сервер включён. Когда не пользуешься — **выключай**.
- **Selectel → Серверы → videophotoAPI → «Выключить» (power off).** Модели и настройки на диске сохраняются; платишь только за диск.
- Утром «Включить». Сервисы поднимутся сами (ComfyUI — systemd-сервис; стек — docker compose; если не поднялись, см. §8).

⚠️ Прерываемый сервер — для разработки. Для боевого сервиса с клиентами бери **обычный** (см. почему — в чате/ТЗ).

После включения проверь, что всё живо:
```
systemctl is-active comfyui
cd /root/ai-generation-api && docker compose ps
curl -s http://localhost:8000/health
```

---

## 4. Архитектура (коротко)

```
mode (YAML) → workflow (JSON, граф ComfyUI) → model (models.yaml → файл .safetensors)
```
Запрос с `mode` → система подставляет в `workflow` фото/промт/параметры → ComfyUI генерирует → результат.
Подробнее — в [HOWTO_MODELS_AND_EDITING.md](HOWTO_MODELS_AND_EDITING.md) §0.

---

## 5. Как сгенерировать — 2 способа

### 5.1 Через тест-страницу (для проверки руками)
1. Открой `http://178.130.61.39:8000/ui/test.html`.
2. Ключ уже вписан; выбери **Тип** (photo/video) и **Режим** из списка.
3. Прикрепи фото (и референс — для фото-режимов).
4. **Сгенерировать** → внизу появится результат или текст ошибки.

### 5.2 Через API (как будет на сайте)
```
1) POST /uploads   (файл)            → image_url
2) POST /generate  (mode + image_url) → task_id
3) GET  /tasks/{task_id}             → статус → result_url
```
Полные примеры запросов/кода — в [VIDEO_API_INTEGRATION.md](VIDEO_API_INTEGRATION.md) §3 и §«пример кода».

---

## 6. Управление режимами (40 видов)

**Список режимов:** `GET /modes?task_type=video` (или photo).

**Где лежат:** `config/modes/video/VIDEO_VARIATION_1..40.yaml`, `config/modes/photo/*.yaml`.

**Редактировать промт режима:**
1. `nano /root/ai-generation-api/config/modes/video/VIDEO_VARIATION_13.yaml`
2. Менять **только** `prompt_template` / `negative_prompt` / `params`.
   - НЕ удалять якоря «keep SAME face/identity/location».
   - НЕ удалять `{{ metadata.change | default('') }}`.
3. Применить: `cd /root/ai-generation-api && docker compose restart worker`.
4. Проверить промт без генерации: `POST /modes/VIDEO_VARIATION_13/preview`.

**Добавить новый режим:** скопируй любой YAML, дай новый `id`, поменяй промт — он сам появится в `/modes`.

**Что значат параметры:** `steps` (качество/скорость), `cfg` (с lightning = 1.0), `width/height`, `num_frames/fps`, `seed`. Подробно — HOWTO §7.

---

## 7. Управление моделями (смена/добавление)

Кратко:
1. Скачать файл **на сервер** в нужную папку `/root/ComfyUI/models/<тип>/` (`wget -c -P ...`).
2. Указать: `models.yaml` (та же архитектура) **или** новый `workflows/*.json` (другой движок).
3. `systemctl restart comfyui` + `docker compose restart worker`.
4. Тест.

Полная пошаговая инструкция с папками, токенами HF и примерами — в **[HOWTO_MODELS_AND_EDITING.md](HOWTO_MODELS_AND_EDITING.md)**.

---

## 8. Эксплуатация: сервисы, логи, обновления

**ComfyUI (генерация):**
```
systemctl status comfyui          # состояние
systemctl restart comfyui         # перезапуск
journalctl -u comfyui --no-pager | tail -40   # логи/ошибки нод
```

**Наш стек (API/worker/db/redis):**
```
cd /root/ai-generation-api
docker compose ps                 # статус контейнеров
docker compose restart worker     # применить правки конфигов
docker compose up -d --build      # пересобрать (после смены КОДА)
docker compose logs --tail=40 worker   # логи генерации
```

**Обновить проект (правил на ПК):**
```
# на ПК:
git push
# на сервере:
cd /root/ai-generation-api && git pull && docker compose restart worker
```

**Сбросить зависшие задачи:**
```
docker compose exec -T worker celery -A app.queues.celery_app purge -f
docker compose restart worker
```

---

## 9. Подключение сайта (другой сервер)

1. **Создать API-ключ:**
   ```
   cd /root/ai-generation-api && docker compose exec -T api python -m scripts.create_api_key "Site"
   ```
2. Со своего сервера слать запросы с заголовком `X-API-Key`:
   - `GET /modes?task_type=video` → показать режимы;
   - `POST /uploads` → `image_url`;
   - `POST /generate` → `task_id`;
   - поллить `GET /tasks/{id}` **или** принимать **callback** (подписан HMAC, секрет `WEBHOOK_SIGNING_SECRET` из `.env`).
3. **Оплата/возврат:** списываешь при старте; при `failed` — возврат по `request_id`.

Готовый пример кода + контракт — в [VIDEO_API_INTEGRATION.md](VIDEO_API_INTEGRATION.md).

**Безопасность для боя:** HTTPS перед `:8000`, фаервол (пускать `:8000` только с IP сайта), закрыть `:8188` наружу.

---

## 10. Безопасность контента (обязательно для adult-платформы)

- Включить **21+ / верификацию возраста** перед генерацией.
- Согласие; **запрет** загрузки лиц реальных людей в сексуальный контент (anti-NCII).
- Логирование обращений.

---

## 11. Что сохраняется при выключении

- Модели (`/root/ComfyUI/models`), проект (`/root/ai-generation-api`), БД (volume Postgres) — **на диске, сохраняются** при power-off.
- Удаляется только при удалении сервера/диска. Перед удалением сервера — выгрузи нужное.

---

## 12. Быстрый траблшутинг

| Симптом | Что сделать |
|---|---|
| Тест-страница не открывается | сервер включён? `systemctl is-active comfyui`; `docker compose ps` |
| Задача висит/`failed` | `docker compose logs --tail=40 worker`; `journalctl -u comfyui | tail -40` |
| `model not found` | проверить имя файла (`ls` папки) и `models.yaml`/workflow |
| Чёрное видео | ComfyUI должен идти с `--fp32-vae` (уже в bootstrap) |
| OOM (нехватка памяти) | не должно быть `--highvram`; снизить разрешение/кадры |
| Правки не применились | `git pull` (если правил на ПК) + `docker compose restart worker` |
| Кривые руки на видео | поднять `steps` (4→8), `cfg=1.0` |

---

## 13. Карта документов
- **USER_GUIDE.md** (этот) — как пользоваться, эксплуатация.
- **HOWTO_MODELS_AND_EDITING.md** — смена моделей, правка промтов (детально).
- **VIDEO_API_INTEGRATION.md** — API, 40 режимов, подключение сайта (детально).
- **PROGRESS.md** — журнал состояния сервера/настроек.
