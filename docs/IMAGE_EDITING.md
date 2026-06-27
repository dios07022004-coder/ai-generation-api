# ТЗ: редактирование изображений (image editing)

Точное техническое задание: как разработать редактирование изображений на базе
этого API, как строить промтинг под редактирование и как добиться корректного
результата. Редактирование = `photo`-задача + режим (YAML) + ComfyUI-workflow.
Ядро не меняется; нужно одно добавление в контракт — **маска** (`mask_url`).

---

## 1. Что входит в «редактирование» (охват)

| Категория | Что делает | Нужна маска? | Модель/метод (в workflow) |
|---|---|---|---|
| **Inpaint (правка области)** | заменить/перерисовать выделенную зону | да | Flux Fill, SDXL-Inpaint, BrushNet |
| **Удаление объекта** | стереть объект, дорисовать фон | да | LaMa / inpaint |
| **Замена объекта** | заменить предмет на другой по промту | да | inpaint + промт |
| **Замена фона** | вырезать субъект, новый фон | авто-маска | SAM2/RMBG + inpaint/композит |
| **Outpaint (расширение)** | дорисовать за границами кадра | авто (паддинг) | inpaint по расширенному холсту |
| **Ретушь/реставрация** | убрать дефекты, апскейл, восстановить лицо | нет/частично | CodeFormer/GFPGAN + RealESRGAN |
| **Релайт/цвет** | сменить свет, тон, время суток | нет | IC-Light / img2img low denoise |
| **Стиль** | перенос стиля, сохранив структуру | нет | img2img + IP-Adapter + ControlNet |
| **Инструкция (instruct)** | «сделай ночь», «надень очки» — текстом | нет | Flux Kontext / Qwen-Image-Edit / InstructPix2Pix |
| **Лицо/идентичность** | заменить/сохранить лицо в зоне | да (зона лица) | InstantID/PuLID/ReActor |

Каждая категория = отдельный режим-файл (`config/modes/photo/EDIT_*.yaml`) со своим
workflow. Добавление новой категории = новый YAML + workflow, без правки кода.

---

## 2. Контракт API для редактирования

Редактирование использует существующий `POST /generate` с `task_type: "photo"`.
Входы:

| Поле | Назначение | Статус |
|---|---|---|
| `image_url` | исходное изображение (что редактируем) | ✅ есть |
| `mask_url` | **маска области правки** (бел=править, чёрн=сохранить) | ✅ реализовано (миграция 0003) |
| `reference_urls` | референсы (стиль/новый объект/лицо) | ✅ есть |
| `metadata` | параметры инструкции (напр. `{"instruction":"make it night"}`) | ✅ есть |
| `mode` | какой тип правки (EDIT_INPAINT и т.п.) | ✅ есть |
| `params` (в режиме) | denoise, рост/размытие маски, steps, seed | ✅ есть |

Маска готовится одним из способов:
1. фронт рисует маску → загружает через `POST /uploads` → `mask_url`;
2. авто-маска внутри workflow (SAM2/RMBG по тексту/клику) — тогда `mask_url` не нужен.

### 2.1 Реализовано ✅ (поле `mask_url` уже в контракте)
`mask_url` проведён сквозь всю цепочку (schema → model → миграция `0003` →
task_service → provider → worker → comfyui ctx) и покрыт тестами
(`tests/test_image_editing.py`). В ComfyUI-workflow доступен как `{{mask_url}}`.
`POST /uploads` принимает PNG (маска — это PNG), отдельный эндпоинт не нужен.

Остаётся только собрать сами **edit-workflow** в ComfyUI (inpaint/instruct и т.п.,
см. §4) и создать `EDIT_*` режимы (§3) — код уже всё поддерживает.

---

## 3. Каталог режимов редактирования (пример)

```
config/modes/photo/
  EDIT_INPAINT.yaml          # правка выделенной области по промту
  EDIT_REMOVE_OBJECT.yaml    # удалить объект (маска) → дорисовать фон
  EDIT_BG_REPLACE.yaml       # заменить фон (авто-маска субъекта)
  EDIT_OUTPAINT.yaml         # расширить кадр
  EDIT_RETOUCH.yaml          # ретушь + восстановление лица + апскейл
  EDIT_RELIGHT.yaml          # сменить свет/время суток
  EDIT_STYLE.yaml            # перенос стиля с сохранением структуры
  EDIT_INSTRUCT.yaml         # правка текстовой инструкцией (Kontext/Qwen-Edit)
  EDIT_FACE.yaml             # правка/сохранение лица в зоне
```

Пример режима inpaint:
```yaml
id: EDIT_INPAINT
type: photo
enabled: true
model: edit_inpaint_model        # ключ из config/models.yaml (Flux Fill / SDXL Inpaint)
workflow: edit_inpaint           # config/workflows/edit_inpaint.json
params:
  denoise: 0.85                  # сила правки в маске (см. §5)
  mask_blur: 8                   # размытие краёв маски (мягкий стык)
  mask_grow: 6                   # расширение маски в пикселях
  steps: 30
  seed: 0
preserve_face: false
prompt_template: |
  {{ metadata.target }}          # что должно появиться в области
negative_prompt: |
  artifacts, seam, blurry, distorted, watermark
```

Пример instruct-режима:
```yaml
id: EDIT_INSTRUCT
type: photo
model: edit_instruct_model       # Flux Kontext / Qwen-Image-Edit
workflow: edit_instruct
params: { steps: 28, seed: 0, guidance: 2.5 }
prompt_template: |
  {{ metadata.instruction }}     # напр. "change daytime to night, keep the person"
negative_prompt: ""
```

---

## 4. Workflow в ComfyUI (логика правки)

Логика — в `config/workflows/*.json` (экспорт «Save API Format»), не в коде.
Плейсхолдеры: `{{image_url}}`, `{{mask_url}}`, `{{prompt}}`, `{{negative}}`,
`{{reference_0}}…`, `{{param.denoise}}`, `{{param.mask_blur}}`, `{{seed}}` и т.д.

Опорные графы:
- **Inpaint:** Load image → Load mask `{{mask_url}}` → GrowMask/BlurMask →
  VAEEncodeForInpaint → KSampler(`denoise={{param.denoise}}`) → VAEDecode →
  **композит только по маске** обратно в оригинал → SaveImage.
- **Удаление объекта:** маска объекта → LaMa или inpaint с промтом «empty
  background» → композит.
- **Замена фона:** SAM2/RMBG авто-маска субъекта → инверсия → новый фон (генерация
  или референс) → композит субъекта поверх → согласование света (IC-Light).
- **Outpaint:** Pad image + расширенная маска краёв → inpaint → SaveImage.
- **Instruct:** Flux Kontext/Qwen-Edit нода: вход = `{{image_url}}` + текст
  `{{prompt}}` → результат. Маска не нужна.
- **Ретушь:** FaceDetailer (CodeFormer/GFPGAN) + RealESRGAN upscale.

Ключ корректности: **результат композитится в оригинал ПО МАСКЕ**, чтобы
неотредактированные зоны остались пиксель-в-пиксель (см. §6).

---

## 5. Параметры качества (что и как крутить)

| Параметр | Где | Рекоменд. | Эффект |
|---|---|---|---|
| `denoise` | params | inpaint 0.7–0.9; релайт/стиль 0.3–0.6; instruct n/a | сила изменения; ниже = ближе к оригиналу |
| `mask_blur` | params | 4–12 px | мягкий стык, нет видимого шва |
| `mask_grow` | params | 4–10 px | захватить край объекта/тени |
| `steps` | params | 25–35 (turbo 6–8) | детализация vs скорость |
| `seed` | params | фикс для воспроизв. | повторяемость |
| разрешение | workflow | править в нативном; апскейл после | резкость без артефактов |
| region-only | workflow | обрабатывать кроп маски | быстрее и чётче в зоне |
| guidance/cfg | params | SDXL 4–6, Flux 2.5–3.5 | следование промту |

Правило: **минимальный denoise, дающий нужное изменение** — так сохраняется
максимум оригинала и нет «перерисовки» соседних зон.

---

## 6. Как добиться КОРРЕКТНОЙ работы (чек-лист корректности)

1. **Сохранение неизменных зон:** финальный композит = `оригинал*(1-маска) +
   результат*маска`. Без этого модель «перетряхивает» всё фото.
2. **Совпадение размеров** image и mask: если не совпадают — ресайз маски к фото;
   валидировать на входе (иначе сдвиг правки).
3. **Мягкая маска:** blur+grow убирают шов; иначе видна «заплатка».
4. **Согласование цвета/света** при замене фона/объекта (IC-Light / color match),
   иначе вставка «не родная».
5. **Лицо:** для правок рядом с лицом — FaceDetailer/InstantID, иначе деградирует.
6. **Безопасность 21+** применяется и к редактированию (проверка `image_url` и
   референсов ДО правки) — уже встроено (`SAFETY_PROVIDER`).
7. **Идемпотентность** по `request_id`; **ошибка → failed-callback → возврат
   средств** на SRC (как у генерации).
8. **Валидация входа:** для inpaint-режимов `image_url` обязателен; для масочных —
   `mask_url` обязателен (иначе 422 на постановке).
9. **Превью промта** без GPU: `POST /modes/{id}/preview` — проверить, что промт/
   инструкция собираются корректно.

---

## 7. Промтинг для редактирования (как строить)

Промт редактирования ≠ промт генерации. Цель — **описать целевое состояние зоны
и что сохранить**, а не всю сцену заново.

Принципы:
- **Inpaint/замена:** в `prompt_template` пиши ТОЛЬКО то, что должно оказаться в
  маске: `"a red leather handbag, studio light, same angle"`. Не описывай всё фото.
- **Instruct-модели (Kontext/Qwen-Edit):** пиши императив + что сохранить:
  `"change the season to winter with snow, keep the person and pose unchanged"`.
- **Сохранение:** добавляй якоря — `"keep the same face/lighting/perspective"`.
- **Негатив:** `seam, artifacts, double object, distorted, color mismatch, blurry`.
- **Переменные:** прокидывай детали через `metadata` →
  `{{ metadata.target }}`, `{{ metadata.instruction }}`, `{{ metadata.bg }}` и т.п.
- **denoise + промт связаны:** сильная правка = выше denoise + конкретный промт;
  лёгкая коррекция = низкий denoise + короткий промт.
- Тестируй: `/preview` (текст) → 3–4 сида (визуал) → подбор `denoise`/`mask_blur`.

Шаблон режима «замена фона» с переменными:
```yaml
prompt_template: |
  {{ metadata.bg | default('clean studio background') }}, matching light and shadows,
  keep the subject unchanged
negative_prompt: |
  halo, cutout edges, color mismatch, seam, blurry
params: { denoise: 0.9, mask_blur: 10, mask_grow: 6 }
```

---

## 8. Поток (фронт → SRC → GEN)

```
1. Юзер: загрузил фото, (нарисовал маску), выбрал тип правки, ввёл инструкцию.
2. Фронт → SRC.
3. SRC: проверка прав/баланса → резерв средств.
4. SRC → GEN: POST /uploads (фото) → image_url; POST /uploads (маска) → mask_url.
5. SRC → GEN: POST /generate {task_type:"photo", mode:"EDIT_INPAINT",
              image_url, mask_url, reference_urls?, metadata:{target/instruction},
              request_id, callback_url}.
6. GEN: safety 21+ → workflow правки → результат в S3.
7. GEN → SRC: callback (HMAC). completed → списать + отдать; failed → возврат.
```

---

## 9. Тест-план

- Unit: приём `mask_url`, хранение в задаче, проброс в провайдер (как для refs).
- Integration (mock): EDIT_* режимы проходят `/preview` и `/generate`→`completed`.
- Корректность (на GPU): шов/края (мягкая маска), неизменность зон вне маски
  (diff с оригиналом = 0 вне маски), совпадение размеров image/mask, лицо рядом
  с правкой не деградирует, замена фона со светосогласованием.
- Безопасность: фото с лицом <21 → блок до правки → failed-callback.
- Идемпотентность: повтор `request_id` не плодит правок.

---

## 10. Этапы разработки (roadmap)

1. **Контракт:** добавить `mask_url` (см. §2.1) + миграция + тесты. (½ дня)
2. **Режимы-заглушки:** создать `EDIT_*` YAML (промты пустые/TODO). (½ дня)
3. **Workflows (ComfyUI, на GPU):** собрать inpaint/instruct/bg/outpaint графы с
   плейсхолдерами; выбрать модели (Flux Fill/Kontext, SDXL-Inpaint, SAM2, LaMa,
   RealESRGAN). (основное время — здесь)
4. **Промтинг и подбор params:** denoise/mask_blur/steps по категориям. (итеративно)
5. **Корректность:** композит по маске, валидация размеров, светосогласование.
6. **Релиз:** safety+биллинг (резерв→списание→возврат) уже работают.

---

## 11. Критерии приёмки

- [ ] `mask_url` принимается, хранится, проброшен в workflow (`{{mask_url}}`).
- [ ] Для масочных режимов отсутствие `mask_url` → 422; для inpaint без `image_url` → 422.
- [ ] Зоны вне маски не меняются (pixel-diff = 0 вне маски).
- [ ] Нет видимого шва (мягкая маска), цвет/свет согласованы.
- [ ] Instruct-режим меняет по тексту, сохраняя указанное.
- [ ] Safety 21+ срабатывает до правки; ошибка → failed-callback → возврат средств.
- [ ] Промты редактируются в YAML, проверяются `/preview`, применяются `/reload`.
- [ ] (Прод) выбранные модели дают качество на целевом GPU (A30/A100).
```
