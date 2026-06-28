# PROGRESS / журнал работы (resume отсюда)

Последнее обновление: 2026-06-28 (вечер). Файл — чтобы продолжить без потерь.

## Сервер (Selectel)
- GPU: **A30 24 ГБ**, Ubuntu 24.04 GPU Driver 580 Open. Доступ — **веб-консоль Selectel**
  (SSH с ПК не настроен, key-only). Публичный IP: **45.80.129.30**.
- На выключение на ночь: **«Выключить» (power off)** — НЕ удалять (сохранятся модели/настройки).
  Платишь только за диск+IP. Утром «Включить».
- Проект: `/root/ai-generation-api`. ComfyUI: `/root/ComfyUI` (systemd `comfyui`, `--listen 0.0.0.0 --port 8188`).
- Порт 8000 открыт (API), 8188 (ComfyUI) — временно для UI, держать закрытым.
- Тестовая страница: http://45.80.129.30:8000/ui/test.html
- API-ключ (тест): `sk_JxTRdKuSkUg_5AuCJPgLPVGUpaEnccjV2szaS-SqVUY`
- `.env`: GENERATION_PROVIDER=comfyui, SAFETY_PROVIDER=**none** (21+ выключен!), PUBLIC_BASE_URL=http://45.80.129.30:8000

## Что РАБОТАЕТ
- Полный пайплайн фото через API (загрузка → очередь → ComfyUI → результат → показ на странице).
- **InstantID (сохранение лица) работает** через API. Чекпоинт реализма **RealVisXL_V5.0_fp16.safetensors**.
- **FaceDetailer** добавлен в ComfyUI-граф → реализм «как настоящее фото» (поры, плёнка). (в ComfyUI UI; в API ещё не зашит — см. ниже).
- Режимы: SDXL_TEST, SDXL_IMG2IMG, PHOTO_MODE_1..5 (InstantID), PHOTO_TEMPLATE (выключен, ждёт workflow).

## Модели на сервере (/root/ComfyUI/models)
- checkpoints: sd_xl_base_1.0, RealVisXL_V5.0_fp16
- instantid/ip-adapter.bin, controlnet/instantid.safetensors, insightface/models/antelopev2 (выровнено!)
- ultralytics/bbox/face_yolov8m.pt, sams/sam_vit_b_01ec64.pth (FaceDetailer)
- (в процессе скачивания для премиум-режима): controlnet/openpose-sdxl, controlnet/depth-sdxl,
  ipadapter/ip-adapter_sdxl_vit-h, clip_vision/CLIP-ViT-H-14

## ВАЖНЫЕ уроки/фиксы (не потерять)
- ComfyUI listen 0.0.0.0; docker-compose extra_hosts host.docker.internal:host-gateway.
- Подстановка плейсхолдеров JSON-экранируется (multiline промты).
- antelopev2 — файлы .onnx прямо в .../antelopev2/ (не вложенно).
- **Один GPU**: при тюнинге в ComfyUI выключать воркер (`docker compose stop worker`), потом `start worker`.
- **InstantID копирует позу/наклон головы со входного фото.** Хочешь произвольную позу → нужен ControlNet OpenPose (отдельный референс).
- Промт InstantID: позитив = ОПИСАНИЕ СЦЕНЫ (не «keep face»). Реализм = «candid amateur photo, phone,
  natural light, visible skin pores, film grain»; негатив короткий + airbrushed/smooth skin/studio lighting.

## ТЕКУЩАЯ ЗАДАЧА (resume завтра отсюда)
Собираем **премиум-режим «копирование с референса»** (PHOTO_TEMPLATE):
лицо/тело/локация — с фото юзера; поза/взгляд/одежда/сцена/2-й персонаж — с референса.
Строим инкрементально на рабочем InstantID-графе:
1. ✅/⏳ **Шаг 1: скачать модели** (openpose-sdxl, depth-sdxl, ip-adapter_sdxl_vit-h, CLIP-ViT-H-14) — см. docs/ADVANCED_WORKFLOWS.md.
2. ⏳ **Шаг 2: ControlNet OpenPose** (поза/взгляд с референса):
   ноды Load Image(референс) → DWPreprocessor → ControlNetLoader(openpose-sdxl) → ControlNetApplyAdvanced
   (вставить МЕЖДУ ApplyInstantID и KSampler), strength ~0.8.
3. ⏳ **Шаг 3: IP-Adapter** (одежда/стиль/2-й персонаж с референса).
4. ⏳ **Шаг 4: ControlNet Depth** (композиция/расположение 2-го).
5. ⏳ Экспорт «Save (API Format)» → прислать → зашить в `config/workflows/photo_template.json` → включить PHOTO_TEMPLATE.

## PENDING (после премиум-режима)
- Реализм InstantID: экспортировать текущий граф с FaceDetailer → зашить в `photo_instantid.json` (чтобы PHOTO_MODE_x были реалистичны через API).
- Видео: нода ComfyUI-LTXVideo = IMPORT FAILED (kornia `pad`) — чинить/заменить (Wan/CogVideoX).
- Включить 21+: поставить insightface+onnxruntime в контейнер воркера, SAFETY_PROVIDER=insightface.
- Подключить сайт: docs/CURSOR_INTEGRATION.md.

## Рабочий цикл доводки
ComfyUI (UI) собрать/настроить → «Save (API Format)» экспорт → отдать ассистенту →
зашивается в config/workflows/*.json с плейсхолдерами → commit → работает через API.
Плейсхолдеры: {{image_name}} (лицо), {{reference_0_name}} (референс), {{prompt}}, {{negative}},
{{seed}}, {{reference_strength}}, {{param.*}}, {{model.name}}.
