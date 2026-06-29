# Ops Scripts: Models + 40 Modes

Набор скриптов для эксплуатации без изменения Python/API.

## 1) Проверка здоровья

```bash
bash scripts/ops/check_runtime_health.sh
```

## 2) Массовая загрузка моделей

```bash
cp scripts/ops/model_manifest.example.tsv scripts/ops/model_manifest.tsv
# Заполнить URL в model_manifest.tsv
bash scripts/ops/download_models_from_manifest.sh scripts/ops/model_manifest.tsv
```

`target_subdir` в манифесте:
- `checkpoints`
- `diffusion_models`
- `loras`
- `vae`
- `text_encoders`
- `clip_vision`
- `controlnet`
- `ipadapter`

## 3) Применить изменения конфигов

```bash
# только worker
bash scripts/ops/apply_config_changes.sh

# worker + comfyui (если меняли файлы моделей)
RESTART_COMFYUI=1 bash scripts/ops/apply_config_changes.sh

# worker + API reload
RELOAD_URL="http://localhost:8000/admin/modes/reload" \
INTERNAL_JWT="<internal-jwt>" \
bash scripts/ops/apply_config_changes.sh
```

## 4) Валидация workflow и 40 режимов

```bash
python scripts/ops/validate_video_workflow.py --workflow config/workflows/video_i2v.json
python scripts/ops/validate_video_modes.py
```

Установка экспортированного из ComfyUI workflow в API:

```bash
bash scripts/ops/install_video_workflow.sh /tmp/video_i2v_export.json
```

Preview для всех 40 режимов:

```bash
python scripts/ops/validate_video_modes.py \
  --api-base-url http://localhost:8000 \
  --api-key "sk_..." \
  --image-url "https://example.com/test.jpg"
```

Smoke generate для всех 40 режимов:

```bash
python scripts/ops/validate_video_modes.py \
  --api-base-url http://localhost:8000 \
  --api-key "sk_..." \
  --image-url "https://example.com/test.jpg" \
  --smoke \
  --smoke-timeout-seconds 240
```
