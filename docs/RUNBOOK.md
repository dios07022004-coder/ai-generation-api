# Runbook: развернуть на GPU-сервере (своими руками)

Для сервера Selectel A30 24GB, Ubuntu 24.04 GPU Driver 580 Open. SSH: `ssh root@<IP>`.

## Шаг 1. Залить проект на GitHub (один раз, у себя в PowerShell)
```powershell
cd C:\Users\dios0\ai-generation-api
git push -u origin main      # remote уже настроен на твой репозиторий
```

## Шаг 2. Подключиться к серверу и склонировать
```bash
ssh root@<IP>
git clone https://github.com/dios07022004-coder/ai-generation-api.git /root/ai-generation-api
cd /root/ai-generation-api
```
(приватный репо → Git попросит логин/токен GitHub)

## Шаг 3. Автоустановка (Docker + ComfyUI + наш стек + ключ)
```bash
bash scripts/bootstrap_gpu.sh
```
Скрипт сам: поставит Docker (в образе 580 его нет), ComfyUI + ноды, скачает SDXL,
поднимет `docker compose`, сгенерит секреты в `.env`, выдаст API-ключ.
> Часть моделей (InstantID/LTX) — докачать вручную (скрипт подскажет пути).

## Шаг 4. Быстрый тест «реальная картинка» (SDXL, без лица)
Чтобы сразу увидеть результат на скачанном SDXL, временно переключи один режим на
простой workflow: в `config/modes/photo/PHOTO_MODE_1.yaml` поставь
```yaml
model: photo_generation_model     # sd_xl_base_1.0.safetensors
workflow: sdxl_img2img            # готовый рабочий граф
```
Применить: `POST /admin/modes/reload` (Bearer internal-JWT из `scripts.mint_internal_token`).
Затем `POST /generate` (task_type=photo, mode=PHOTO_MODE_1, image_url) → увидишь
реальное фото в `result_url`.

## Шаг 5. Апгрейд до сохранения лица (InstantID) и видео (LTX)
В ComfyUI (туннель `ssh -L 8188:127.0.0.1:8188 root@<IP>` → http://localhost:8188):
собери workflow InstantID (фото) и i2v/LTX (видео), экспортируй «Save (API Format)»
в `config/workflows/photo_instantid.json` и `video_i2v.json`, используя плейсхолдеры
(`{{prompt}} {{negative}} {{image_name}} {{mask_name}} {{reference_0_name}} {{seed}}
{{param.steps}} {{reference_strength}}`). Верни режимам `workflow: photo_instantid` и
`video_i2v`, сделай reload. Теперь промт → результат с сохранённым лицом.

## Безопасность сервера
- Группа безопасности: открыть 22 (твой IP) и 8000 (IP сервера-источника); ComfyUI 8188 — НЕ наружу.
- Прод: поставить HTTPS-прокси (nginx/caddy) на 443 → api:8000.

## Не забыть про деньги
Сервер «Непрерываемый» — тарифицируется, пока существует. Закончил тест —
останови/удали в панели Selectel.
