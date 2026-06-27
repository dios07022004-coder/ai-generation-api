# Промтинг: где править и насколько это сложно

TL;DR: чтобы изменить поведение режима, ты правишь **один YAML-файл**. Кода
касаться не нужно. Сложность — **низкая** (уровень «отредактировать текстовый
файл»). Единственная по-настоящему техническая часть — ComfyUI workflow для
сохранения лица, и её делают один раз.

---

## 1. Что и где править

```
config/
  models.yaml                         # какие модели стоят за логическими именами
  modes/
    photo/PHOTO_MODE_1.yaml ... _5     # 5 фото-режимов  ← правишь это
    video/VIDEO_VARIATION_1.yaml ...   # 40 видео-вариаций ← и это
  workflows/
    photo_instantid.json               # как сохранять лицо (делается 1 раз)
    video_i2v.json
```

### Файл режима — единственное, что нужно для промтинга

```yaml
id: PHOTO_MODE_1
type: photo
enabled: true                # вкл/выкл режим
model: photo_face_model      # ключ из models.yaml
workflow: photo_instantid    # имя файла из config/workflows/

params:                      # числовые параметры генерации
  width: 1024
  height: 1024
  steps: 30
  seed: 0

preserve_face: true          # флаги для workflow
reference_strength: 0.8

# >>> ВОТ ЗДЕСЬ ПИШЕШЬ ПРОМТ <<<
prompt_template: |
  portrait of a person, cinematic light, keep the same face from reference
negative_prompt: |
  lowres, blurry, deformed, watermark
```

**Сложность правки промта: 🟢 низкая.** Меняешь `prompt_template` /
`negative_prompt` / `params` — и всё.

### Переменные в шаблоне (Jinja2)

В промт можно подставлять данные запроса:

| Переменная | Что это |
|---|---|
| `{{ image_url }}` | URL исходного фото |
| `{{ user_id }}` | id пользователя |
| `{{ request_id }}` | id запроса |
| `{{ metadata.КЛЮЧ }}` | любое поле из `metadata` запроса |

Пример: `prompt_template: "portrait of {{ metadata.subject }}, neon style"`.

> Если переменной нет в запросе — режим даст понятную ошибку (422) ещё на
> предпросмотре/постановке, а не молча сгенерит мусор.

---

## 2. Как проверить промт без запуска GPU (оптимизация)

Эндпоинт **`POST /modes/{id}/preview`** рендерит промт на тестовых данных и
показывает результат/ошибку шаблона — мгновенно, без генерации:

```bash
curl -X POST http://host/modes/PHOTO_MODE_1/preview \
  -H "X-API-Key: <key>" -H "Content-Type: application/json" \
  -d '{"image_url":"https://x/a.jpg","metadata":{"subject":"cat"}}'
# → {"prompt":"portrait of cat, neon style", "negative_prompt":"...", ...}
```

Цикл правки: изменил YAML → `preview` → доволен → `POST /admin/modes/reload`
(применить без перезапуска) → готово.

---

## 3. Применить изменения без перезапуска

```bash
# нужен internal-токен (служебный), API-ключ тут не подходит:
TOKEN=$(python -m scripts.mint_internal_token --subject ops)
curl -X POST http://host/admin/modes/reload -H "Authorization: Bearer $TOKEN"
# → {"status":"reloaded","count":45}
```

В Docker/K8s, если режимы запечены в образ, вместо reload проще выкатить новый
образ; для «горячих» правок монтируй `config/` томом и дёргай reload.

---

## 4. Добавить новый режим

Просто положи новый файл `config/modes/photo/PHOTO_MODE_6.yaml` (или
`video/VIDEO_VARIATION_41.yaml`) с уникальным `id` и сделай reload. Ядро менять
не нужно — оно само находит файлы.

---

## 5. Сохранение лица — единственная «техническая» часть

| Часть | Сложность | Кто делает |
|---|---|---|
| Текст промта, негатив, params | 🟢 низкая | контент-менеджер |
| Вкл/выкл, добавление режима | 🟢 низкая | контент-менеджер |
| ComfyUI workflow (InstantID/PuLID) | 🟠 средняя, **разово** | инженер с ComfyUI |

Логика «сохранить лицо/персонажа» живёт не в коде, а в `config/workflows/*.json`
(экспорт из ComfyUI, ноды InstantID/IP-Adapter/PuLID + загрузка
`{{image_url}}`). Подробно — `config/workflows/README.md`. После того как
workflow собран один раз, все режимы просто ссылаются на него по имени.

---

## Итог по сложности

- Повседневный промтинг (то, что делаешь ты): **🟢 низкая** — правка одного YAML
  + `preview` + `reload`.
- Разовая настройка workflow сохранения лица: **🟠 средняя**, делается один раз
  инженером.
- Архитектура уже максимально упрощена под промтинг: декларативные файлы,
  предпросмотр без GPU, hot-reload, авто-обнаружение режимов.

---

## Пример: МАКСИМАЛЬНОЕ сохранение лица + та же локация

> Важно: текст промта сам по себе НЕ сохраняет личность. Идентичность лица держит
> **workflow** (InstantID / IP-Adapter FaceID / PuLID) + `reference_strength`, а
> локацию — **низкий `denoise`** (img2img) и/или **ControlNet** (depth/lineart) из
> исходного фото. Промт ниже это **усиливает и направляет**. Нужны все три части:
> (1) промт, (2) параметры, (3) ноды в workflow.

Промты пиши **на английском** — модели понимают его точнее.

### Готовый режим (пример файла `config/modes/photo/PHOTO_MODE_X.yaml`)

```yaml
id: PHOTO_MODE_X
type: photo
enabled: true
model: photo_face_model          # SDXL+InstantID или Flux+PuLID
workflow: photo_instantid        # должен содержать: InstantID + ControlNet(depth/lineart) + img2img
params:
  width: 1024
  height: 1024
  steps: 32
  cfg: 4.5
  seed: 0
  denoise: 0.45                  # ← НИЗКИЙ: фон/локация почти не меняются
preserve_face: true
reference_strength: 0.9          # ← ВЫСОКИЙ: максимум идентичности лица (InstantID)

# ================== ПОЗИТИВНЫЙ ПРОМТ (упор на лицо + локацию) ==================
prompt_template: |
  RAW photo of {{ metadata.subject | default('the same exact person from the reference image') }}.
  IDENTITY — keep the SAME face, do not change the person:
  identical facial structure and proportions, same eye shape and eye color,
  same nose, same lips and mouth, same eyebrows, same jawline and cheekbones,
  same skin tone and natural skin texture, same moles/freckles/marks,
  same hairstyle and hair color, same age. The person must be instantly recognizable
  as the same individual.
  LOCATION — keep the SAME background and place exactly as in the source image:
  identical environment, same room/scene, same objects and furniture, same wall,
  same lighting direction and ambience; do not move to a new location, do not change the scenery.
  FRAMING — same composition, same camera angle, same perspective and pose.
  {{ metadata.change | default('only subtle photorealistic enhancement') }}.
  photorealistic, natural lighting, sharp focus on the eyes, high detail,
  professional photography, 85mm lens.

# ================== НЕГАТИВНЫЙ ПРОМТ ==================
negative_prompt: |
  different person, another face, changed identity, face of a stranger,
  face swap to a different person, altered facial features, morphed face,
  distorted face, deformed, asymmetric eyes, extra eyes, plastic skin,
  heavy beauty filter, airbrushed, cartoon, 3d render,
  different background, new location, changed scenery, replaced environment,
  removed objects, added objects, extra people, duplicate face,
  text, watermark, logo, lowres, blurry, jpeg artifacts, bad anatomy,
  extra fingers, mutated hands
```

### Как это работает (3 рычага)
| Рычаг | Значение | Зачем |
|---|---|---|
| `reference_strength` | **0.85–0.95** | сила InstantID/FaceID — чем выше, тем ближе лицо к оригиналу |
| `denoise` | **0.35–0.5** | низкий → фон/локация сохраняются почти без изменений |
| ControlNet (в workflow) | depth + lineart из `{{image_url}}` | жёстко фиксирует геометрию сцены и композицию |

### Тонкая настройка под результат
- Лицо «уплыло» → подними `reference_strength` (0.9→0.95) и/или добавь в workflow
  **FaceDetailer** (восстановление лица).
- Локация изменилась → понизь `denoise` (0.45→0.35) или усиль вес ControlNet.
- Слишком «приклеенный» оригинал, нет нужной правки → чуть подними `denoise` и
  опиши изменение в `{{ metadata.change }}`.
- Для идентичности «1:1» (паспортная точность) — добавь в workflow **ReActor**
  (face-swap) поверх результата.

### Проверка без GPU
```bash
curl -X POST http://host/modes/PHOTO_MODE_X/preview -H "X-API-Key: KEY" \
  -H "Content-Type: application/json" \
  -d '{"image_url":"https://x/a.jpg","metadata":{"change":"change outfit to a business suit"}}'
# вернёт собранный промт — убедись, что якоря "keep the SAME face/location" на месте
```

> Якоря, которые ОБЯЗАТЕЛЬНО оставлять в промте при правках: «same exact person /
> keep the same face» и «keep the same background / location». Меняй только то, что
> в `{{ metadata.change }}`.
