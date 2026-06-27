# Продвинутые workflow: реализм + «копирование с референса»

Эти графы собираются в ComfyUI на GPU (их нельзя написать вслепую). Ниже —
пошаговая сборка. После сборки экспортируй «Save (API Format)» и пришли мне —
я зашью в `config/workflows/*.json` и привяжу к режимам.

Все модели ставь через **Manager → Custom Nodes / Model Manager** (там корректные
ссылки) — это надёжнее ручных URL.

---

## Часть 1. РЕАЛИЗМ «не отличить» (доработка лица)

Цель: к рабочему графу InstantID добавить детализацию кожи/лица + плёночность.

### 1.1 Поставить ноды/модели (через Manager)
- **ComfyUI-Impact-Pack** (даёт ноду **FaceDetailer**) — Manager → Install Custom Nodes → «Impact Pack» → Install → Restart.
- Детектор лица: Manager → Install Models → **`face_yolov8m`** (bbox) и **SAM** (`sam_vit_b`).
- (опц.) **Realism/skin LoRA** — Manager → Install Models, искать «skin»/«realism» (или add_detail).

### 1.2 Добавить FaceDetailer в граф InstantID
После ноды **VAEDecode** (выход картинки) вставь **FaceDetailer**:
- `image` ← выход VAEDecode
- `model`, `clip`, `vae` ← с чекпоинта (как у KSampler)
- `positive`, `negative` ← те же CONDITIONING, что в KSampler
- `bbox_detector` ← нода **UltralyticsDetectorProvider** (`face_yolov8m.pt`)
- `sam_model_opt` ← нода **SAMLoader** (`sam_vit_b`)
- параметры: `denoise 0.4`, `guide_size 512`, `feather 5`
- выход FaceDetailer → **SaveImage**

### 1.3 (опц.) Плёночность и апскейл
- Нода **ImageUpscaleWithModel** (модель `4x-UltraSharp`) → 1.5–2×.
- Лёгкий **film grain** (нода из Impact/постобработки) — добавляет «реальность».
- (опц.) **LoRA Loader** с realism-LoRA между чекпоинтом и InstantID.

### 1.4 Параметры под реализм
- weight (InstantID) **1.0**, cfg **4.0**, steps **35**, sampler **dpmpp_2m**, scheduler **karras**.
- Промт — «любительский» (см. PHOTO_TEMPLATE.yaml).

Собрал → проверил визуально → **Save (API Format)** → пришли мне → зашью в
`photo_instantid.json` (заработает на всех PHOTO_MODE_x).

---

## Часть 2. «КОПИРОВАНИЕ С РЕФЕРЕНСА» (режим PHOTO_TEMPLATE)

Цель: лицо/телосложение/локация — с фото пользователя; поза/одежда/выражение/
второй персонаж — с референс-картинки.

Входы (наш API уже их отдаёт в workflow):
- `{{image_name}}` — фото пользователя (лицо/локация).
- `{{reference_0_name}}` — референс-образец (поза/одежда/второй персонаж).

### 2.1 Поставить модели (через Manager → Model Manager)
- **ControlNet OpenPose SDXL** (поза, в т.ч. второго персонажа).
- **ControlNet Depth SDXL** (композиция/расположение второго персонажа).
- **IP-Adapter SDXL** + **CLIP-Vision** (одежда/стиль).
- Препроцессоры уже есть (`comfyui_controlnet_aux`): **DWPose/OpenPose**, **DepthAnything**.

### 2.2 Схема графа
```
[Фото пользователя {{image_name}}] ─► InstantID (лицо)
                                   └► (img2img latent, denoise={{param.bg_denoise}}) → локация юзера

[Референс {{reference_0_name}}] ─► DWPose preprocessor ─► ControlNet OpenPose (strength={{param.pose_strength}})
                               ├► Depth preprocessor   ─► ControlNet Depth   (strength={{param.depth_strength}})
                               └► IP-Adapter (weight={{param.ipadapter_strength}})  → одежда/стиль/второй персонаж

Всё это → ApplyInstantID/ControlNet chain → KSampler → VAEDecode → FaceDetailer → SaveImage
```
Порядок conditioning: CLIPTextEncode → ControlNetApply(OpenPose) → ControlNetApply(Depth) → ApplyInstantID → KSampler.
IP-Adapter применяется к model (IPAdapterApply) до KSampler.

### 2.3 Параметры (из режима PHOTO_TEMPLATE.yaml)
- `pose_strength` 0.85, `depth_strength` 0.55, `ipadapter_strength` 0.7,
  `reference_strength` (InstantID) 1.0, `bg_denoise` 0.5.
- Крути их, добиваясь баланса «копия с референса ↔ сохранение лица/локации».

### 2.4 Честные ограничения
- **Лицо второго персонажа** конкретно не сохранится (мульти-ID — фронтир); скопируются его поза/одежда/телосложение/расположение.
- **Телосложение** — приблизительно (через позу + IP-Adapter).
- Тяжелее и медленнее (3 conditioning-модуля). A30 справляется.

Собрал → проверил → **Save (API Format)** → пришли мне → зашью в
`config/workflows/photo_template.json` (режим PHOTO_TEMPLATE уже готов и ждёт его).

---

## Плейсхолдеры, которые подставит наш API (используй их в нодах)
`{{prompt}}`, `{{negative}}`, `{{image_name}}` (фото юзера), `{{reference_0_name}}`
(референс), `{{mask_name}}`, `{{seed}}`, `{{reference_strength}}`,
`{{param.steps}}`, `{{param.cfg}}`, `{{param.width}}`, `{{param.height}}`,
`{{param.pose_strength}}`, `{{param.depth_strength}}`, `{{param.ipadapter_strength}}`,
`{{param.bg_denoise}}`, `{{model.name}}`.
