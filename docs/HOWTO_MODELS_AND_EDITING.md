# Подробная инструкция: модели, режимы, редактирование

Эта инструкция — пошагово и максимально подробно: как устроена система, как **добавлять/менять модели**,
как **редактировать режимы и промты**, как **применять изменения** и **проверять**, что всё работает.
Рассчитана на то, что код ты не трогаешь — только конфиги.

---

## 0. Три «слоя» — главное, что нужно понять

Генерация = связка трёх вещей:

```
РЕЖИМ (config/modes/.../*.yaml)
   ├─ model:    → ссылка на МОДЕЛЬ из config/models.yaml
   ├─ workflow: → ссылка на ГРАФ ComfyUI из config/workflows/*.json
   ├─ params:   → числа (шаги, cfg, размер, кадры…)
   └─ prompt_template / negative_prompt → текст промта

МОДЕЛЬ (config/models.yaml)  → логическое имя → имя файла .safetensors + дефолты
ГРАФ   (config/workflows/*.json) → схема нод ComfyUI с «плейсхолдерами»
ФАЙЛ МОДЕЛИ (.safetensors) → лежит в /root/ComfyUI/models/<папка>/
```

Поток: запрос приходит с `mode` → система берёт его YAML → подставляет в `workflow` нужные
картинки/промт/параметры/имя модели → отправляет в ComfyUI → ComfyUI грузит файл модели из своей папки.

**Вывод:** чтобы поменять модель, нужно (1) положить файл в папку ComfyUI и (2) указать его в `models.yaml`
или в `workflow`. Код не трогается.

---

## 1. Карта файлов (где что лежит)

```
/root/ai-generation-api/                ← наш API-проект (git)
  config/
    models.yaml                         ← список моделей (логическое имя → файл)
    modes/
      photo/*.yaml                      ← фото-режимы
      video/VIDEO_VARIATION_1..40.yaml  ← 40 видео-режимов
    workflows/
      *.json                            ← графы ComfyUI (с плейсхолдерами)

/root/ComfyUI/                          ← движок генерации
  models/
    checkpoints/      ← SDXL и пр. (CheckpointLoaderSimple)
    diffusion_models/ ← Wan, Flux (UNETLoader / Load Diffusion Model)
    loras/            ← LoRA
    vae/              ← VAE
    text_encoders/    ← CLIP/T5 (umt5 и пр.)
    clip_vision/      ← CLIP-Vision (для IP-Adapter)
    controlnet/       ← ControlNet
    ipadapter/        ← IP-Adapter
    insightface/      ← inswapper (ReActor)
    facerestore_models/ ← GFPGAN (ReActor)
```

---

## 2. Как скачать модель НА СЕРВЕР (важно: не на ПК)

Модели должны лежать на **сервере** (где ComfyUI), а не на твоём компьютере.
Скачивай прямо в консоли сервера в нужную папку (см. таблицу ниже).

**Куда какой тип:**
| Что за модель | Папка |
|---|---|
| Чекпойнт SDXL/SD1.5 | `/root/ComfyUI/models/checkpoints/` |
| Diffusion-модель (Wan, Flux) | `/root/ComfyUI/models/diffusion_models/` |
| LoRA | `/root/ComfyUI/models/loras/` |
| VAE | `/root/ComfyUI/models/vae/` |
| Текст-энкодер (umt5, t5, clip_l) | `/root/ComfyUI/models/text_encoders/` |
| CLIP-Vision | `/root/ComfyUI/models/clip_vision/` |
| ControlNet | `/root/ComfyUI/models/controlnet/` |
| IP-Adapter | `/root/ComfyUI/models/ipadapter/` |

**Команда (одной строкой):**
```
wget -c -P /root/ComfyUI/models/<ПАПКА> "ПРЯМАЯ_ССЫЛКА_НА_ФАЙЛ.safetensors"
```
- `-c` = докачивать, если оборвётся.
- Для больших файлов быстрее `aria2c`:
```
aria2c -x16 -s16 -c -d /root/ComfyUI/models/<ПАПКА> "ССЫЛКА"
```

**Если модель «закрытая» (gated на HuggingFace, ошибка 401/403):**
нужен токен HF:
```
wget -c --header="Authorization: Bearer hf_ТВОЙ_ТОКЕН" -P /root/ComfyUI/models/<ПАПКА> "ССЫЛКА"
```
(токен: huggingface.co → Settings → Access Tokens; иногда нужно принять лицензию на странице модели).

**Проверить, что файл скачался целиком:**
```
ls -lah /root/ComfyUI/models/<ПАПКА>/
```
(размер должен совпадать с ожидаемым; «обрезанный» файл = битая модель).

---

## 3. Подключить модель — ДВА сценария

### 🟢 Сценарий A — «та же архитектура» (быстро, без графа)
Подходит, когда новая модель того же типа, что текущая (например, другой **SDXL-чекпойнт** вместо RealVisXL),
и текущий workflow читает имя модели через `{{model.name}}`.

1. Скачал файл в нужную папку (см. §2).
2. Открой `config/models.yaml` и поменяй `name`:
   ```yaml
   photo_face_model:
     name: МОЙ_НОВЫЙ_ЧЕКПОЙНТ.safetensors   # ← было RealVisXL_V5.0_fp16.safetensors
     type: image
     steps: 35
     cfg: 4.5
   ```
3. Применить (см. §5).
4. Тест (см. §6).

→ Все режимы, которые ссылаются на `model: photo_face_model`, сразу заработают на новой модели.

### 🟡 Сценарий B — «другой движок/ноды» (нужен новый граф)
Подходит, когда у модели другая архитектура (другие ноды): например другая видео-модель,
Flux вместо SDXL, и т.п.

1. Скачал файлы модели в нужные папки (§2).
2. Открой **ComfyUI** (`http://<IP>:8188`), собери/настрой граф с этой моделью, проверь вживую.
3. Settings → включи **Enable Dev mode** → кнопка **Save (API Format)**.
4. Полученный JSON положи в `config/workflows/<имя>.json` и **впиши плейсхолдеры** (см. §4)
   вместо жёстко зашитых картинок/промтов/сидов.
5. В нужных режимах укажи `workflow: <имя>` (без `.json`).
6. При желании добавь модель в `models.yaml` (для дефолтов steps/cfg) и сошлись `model:`.
7. Применить (§5) и тест (§6).

> Если сам не уверен с плейсхолдерами — просто пришли мне «Save (API Format)» JSON и скажи,
> какая нода = фото пользователя / референс. Я расставлю плейсхолдеры за минуту.

---

## 4. Плейсхолдеры в workflow (как граф получает входные данные)

В JSON-графе вместо конкретных значений ставятся «плейсхолдеры» — система подставит реальные данные:

| Плейсхолдер | Что подставится |
|---|---|
| `{{model.name}}` | имя файла модели из `models.yaml` |
| `{{image_name}}` | фото пользователя (загруженное) |
| `{{reference_0_name}}` | первый референс из `reference_urls` |
| `{{mask_name}}` | маска (для редактирования) |
| `{{driving_url}}` | управляющее видео (перенос движения) |
| `{{prompt}}` | собранный позитивный промт режима |
| `{{negative}}` | негативный промт режима |
| `{{seed}}` | сид |
| `{{param.steps}}`, `{{param.cfg}}`, `{{param.width}}`, `{{param.height}}`, `{{param.num_frames}}`, `{{param.fps}}` | значения из `params` режима |

Пример куска workflow:
```json
"3": { "class_type": "KSampler",
  "inputs": { "seed": {{seed}}, "steps": {{param.steps}}, "cfg": {{param.cfg}},
              "denoise": {{param.bg_denoise}} } }
```
> Многострочные промты экранируются автоматически — JSON не сломается.

---

## 5. Как ПРИМЕНИТЬ изменения (после правок)

Что ты менял → что перезапустить:

| Что изменил | Команда применения |
|---|---|
| `models.yaml`, `modes/*.yaml`, `workflows/*.json` (правил **на сервере**) | `cd /root/ai-generation-api && docker compose restart worker` |
| то же, но правил **на ПК** | на ПК `git push` → на сервере `git pull` → `docker compose restart worker` |
| **скачал/заменил файл модели** в ComfyUI | дополнительно `systemctl restart comfyui` (чтобы ComfyUI увидел новый файл) |
| хочешь без рестарта воркера | `POST /admin/modes/reload` (нужен internal-JWT) |

> `config/` примонтирован в контейнеры — поэтому правки конфигов подхватываются после `restart worker`,
> пересборка (`--build`) НЕ нужна. Пересборка нужна только если менялся **код** (`app/...`).

---

## 6. Как ПРОВЕРИТЬ, что работает

1. **Промт без генерации** (быстро, не тратит GPU):
   ```
   POST /modes/VIDEO_VARIATION_13/preview   { "image_url":"...", "metadata":{} }
   ```
   Вернёт итоговый `prompt`/`negative` — видно ошибки шаблона сразу.
2. **Полный тест:** `http://<IP>:8000/ui/test.html` → выбери режим → прикрепи фото → Сгенерировать.
3. **Логи при ошибке:**
   ```
   docker compose logs --tail=40 worker          # ошибки нашего пайплайна (видна точная причина ComfyUI)
   journalctl -u comfyui --no-pager | tail -40   # ошибки самого ComfyUI (упавшая нода)
   ```

---

## 7. Как РЕДАКТИРОВАТЬ промты правильно

В `config/modes/.../*.yaml` меняй **только**: `prompt_template`, `negative_prompt`, `params`.

**Нельзя удалять «якоря»** — строки, которые держат лицо/идентичность/локацию, например:
```
Keep the SAME face and identity across ALL frames; the person must stay recognizable.
Keep the SAME location and background as in the source image.
```
Если их убрать — лицо/сцена «уплывут».

**`{{ metadata.change | default('') }}`** — сюда подставляется текст из запроса (поле `metadata.change`),
чтобы пользователь мог добавить деталь, не меняя сам режим. Не удаляй эту вставку.

**Параметры (`params`) и их влияние:**
- `steps` — больше = качественнее/медленнее. Для lightning-моделей мало (4–8).
- `cfg` — сила следования промту. **С lightning-LoRA `cfg` должен быть `1.0`** (иначе артефакты).
- `width`/`height` — разрешение (больше = медленнее, тяжелее по памяти).
- `num_frames`/`fps` — длина видео (81 кадр @ 16 fps ≈ 5 c).
- `seed` — `0` = случайный каждый раз; фиксированное число = повторяемый результат.

---

## 8. Частые ошибки и причины (из реального опыта)

| Симптом | Причина | Решение |
|---|---|---|
| `comfyui error: ...Loader: model not found` | имя файла в workflow ≠ реальное имя в папке | поправить имя в workflow / в `models.yaml`; проверить `ls` папки |
| **Чёрное видео/картинка** | NaN в fp16-VAE | запускать ComfyUI с `--fp32-vae` (уже в bootstrap) |
| **OutOfMemory (OOM)** при смене high/low модели | флаг `--highvram` держит обе в VRAM | убрать `--highvram` (уже убран в bootstrap) |
| **Кривые руки/пальцы** | слишком мало шагов | поднять `steps` (4→8) |
| **«Поломалось» после правки CFG** | `cfg≠1.0` при lightning-LoRA | вернуть `cfg: 1.0` |
| Изменения не применились | не перезапущен worker / не сделан `git pull` | `git pull` (если правил на ПК) + `docker compose restart worker` |
| Сервер не видит правки с ПК | забыл `git push` | на ПК `git push`, затем на сервере `git pull` |

---

## 9. Чек-лист «сменить модель» (коротко)
1. `wget -c -P /root/ComfyUI/models/<папка> "<ссылка>"`
2. `ls -lah` — проверить размер файла.
3. `models.yaml` (имя) **или** новый `workflows/*.json` (если другая архитектура).
4. при необходимости — подкрутить промты в `modes/.../*.yaml`.
5. `systemctl restart comfyui` (если менял файлы моделей) + `docker compose restart worker`.
6. `POST /modes/{id}/preview` → тест на `:8000/ui/test.html`.
7. ошибки → `docker compose logs --tail=40 worker` и `journalctl -u comfyui | tail -40`.
