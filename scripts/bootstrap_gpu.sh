#!/usr/bin/env bash
# ============================================================================
#  Авто-установка GPU-сервера под ai-generation-api (Selectel, Ubuntu 24.04
#  GPU Driver 590 Open - Docker). Поднимает: наш стек (api/worker/postgres/redis)
#  + ComfyUI с кастом-нодами и моделями. После — остаётся только вводить промты.
#
#  Запуск (от root):
#    bash scripts/bootstrap_gpu.sh
#
#  Идемпотентен: можно запускать повторно.
# ============================================================================
set -euo pipefail

# --- настройки (поменяй при необходимости) ---------------------------------
REPO_DIR="${REPO_DIR:-/root/ai-generation-api}"
COMFY_DIR="${COMFY_DIR:-/root/ComfyUI}"
HF_TOKEN="${HF_TOKEN:-}"          # токен Hugging Face (для скачивания части моделей)
PUBLIC_BASE_URL="${PUBLIC_BASE_URL:-http://localhost:8000}"

log(){ echo -e "\n=== $* ==="; }

# --- 0. системные зависимости ----------------------------------------------
log "Системные пакеты"
apt-get update -y
apt-get install -y --no-install-recommends git git-lfs python3-venv python3-pip \
    aria2 ffmpeg curl ca-certificates
git lfs install || true

# Docker: в образе "GPU Driver 590 Open - Docker" он есть; в "580 Open" — нет.
if ! command -v docker >/dev/null 2>&1; then
  log "Docker не найден — ставлю Docker + nvidia-container-toolkit"
  curl -fsSL https://get.docker.com | sh
  # NVIDIA Container Toolkit (чтобы контейнеры видели GPU, если понадобится)
  curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
    | gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg || true
  curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
    | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
    > /etc/apt/sources.list.d/nvidia-container-toolkit.list || true
  apt-get update -y && apt-get install -y nvidia-container-toolkit || true
  nvidia-ctk runtime configure --runtime=docker || true
  systemctl restart docker || true
fi

# --- 1. репозиторий проекта -------------------------------------------------
log "Репозиторий проекта"
if [ ! -d "$REPO_DIR/.git" ]; then
  echo "Положи проект в $REPO_DIR (git clone <твой-репо> $REPO_DIR) и перезапусти."
  echo "Или склонируй сейчас:  git clone <URL> $REPO_DIR"
  exit 1
fi
cd "$REPO_DIR"

# --- 2. .env (секреты генерируем, провайдер=comfyui, safety=insightface) -----
log ".env"
if [ ! -f .env ]; then
  cp .env.example .env
  sed -i "s|^GENERATION_PROVIDER=.*|GENERATION_PROVIDER=comfyui|" .env
  sed -i "s|^COMFYUI_URL=.*|COMFYUI_URL=http://host.docker.internal:8188|" .env
  sed -i "s|^SAFETY_PROVIDER=.*|SAFETY_PROVIDER=insightface|" .env
  sed -i "s|^PUBLIC_BASE_URL=.*|PUBLIC_BASE_URL=${PUBLIC_BASE_URL//\//\\/}|" .env
  WS=$(openssl rand -hex 24); JW=$(openssl rand -hex 24)
  sed -i "s|^WEBHOOK_SIGNING_SECRET=.*|WEBHOOK_SIGNING_SECRET=$WS|" .env
  sed -i "s|^INTERNAL_JWT_SECRET=.*|INTERNAL_JWT_SECRET=$JW|" .env
  echo "Секреты сгенерированы. WEBHOOK_SIGNING_SECRET сообщи серверу-источнику."
fi
# чтобы контейнеры видели ComfyUI на хосте:
grep -q host.docker.internal docker-compose.yml || true

# --- 3. ComfyUI + кастом-ноды ----------------------------------------------
log "ComfyUI"
if [ ! -d "$COMFY_DIR" ]; then
  git clone https://github.com/comfyanonymous/ComfyUI "$COMFY_DIR"
fi
cd "$COMFY_DIR"
python3 -m venv venv || true
. venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
# ускорители (по желанию): pip install xformers

log "Кастом-ноды (Manager + InstantID/IPAdapter/ControlNet/Video/LTX)"
cd "$COMFY_DIR/custom_nodes"
clone(){ [ -d "$(basename "$1" .git)" ] || git clone "$1"; }
clone https://github.com/ltdrdata/ComfyUI-Manager.git
clone https://github.com/cubiq/ComfyUI_InstantID.git
clone https://github.com/cubiq/ComfyUI_IPAdapter_plus.git
clone https://github.com/Fannovel16/comfyui_controlnet_aux.git
clone https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git
clone https://github.com/Lightricks/ComfyUI-LTXVideo.git || true
# доустановить зависимости нод:
for d in */ ; do [ -f "$d/requirements.txt" ] && pip install -r "$d/requirements.txt" || true; done

# --- 4. модели (часть требует HF_TOKEN). Качаем в папки ComfyUI -------------
log "Модели (это долго; часть требует Hugging Face токен)"
M="$COMFY_DIR/models"
mkdir -p "$M/checkpoints" "$M/instantid" "$M/controlnet" "$M/insightface/models" \
         "$M/ipadapter" "$M/clip_vision" "$M/loras"
dl(){ aria2c -x8 -s8 -c -o "$2" -d "$3" "$1" || echo "⚠️ не скачалось: $1 (скачай вручную)"; }
# SDXL base (пример; можно заменить на свой чекпоинт):
dl "https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/resolve/main/sd_xl_base_1.0.safetensors" \
   "sd_xl_base_1.0.safetensors" "$M/checkpoints"
echo "TODO(модели): InstantID (ip-adapter.bin + ControlNet), antelopev2, LTX-Video —"
echo "  скачать в соответствующие папки $M/* (см. README нод). Часть — через HF_TOKEN."

deactivate

# --- 5. ComfyUI как сервис (автозапуск, держит модель в VRAM) ---------------
log "systemd-сервис ComfyUI"
cat >/etc/systemd/system/comfyui.service <<UNIT
[Unit]
Description=ComfyUI
After=network.target
[Service]
WorkingDirectory=$COMFY_DIR
ExecStart=$COMFY_DIR/venv/bin/python main.py --listen 127.0.0.1 --port 8188 --highvram
Restart=always
User=root
[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now comfyui

# --- 6. наш стек ------------------------------------------------------------
log "Наш стек (docker compose)"
cd "$REPO_DIR"
docker compose up -d --build

# --- 7. API-ключ для сервера-источника -------------------------------------
log "API-ключ"
sleep 5
docker compose exec -T api python -m scripts.create_api_key "Site" || true

log "ГОТОВО"
cat <<DONE
Дальше:
1) Открой ComfyUI (туннель: ssh -L 8188:127.0.0.1:8188 root@<IP>) → http://localhost:8188
   Загрузи workflow InstantID (фото) и i2v/LTX (видео), проверь, что модели на месте,
   экспортируй "Save (API Format)" в:
     $REPO_DIR/config/workflows/photo_instantid.json
     $REPO_DIR/config/workflows/video_i2v.json
   Плейсхолдеры: {{prompt}} {{negative}} {{image_url}} {{mask_url}} {{reference_0}}
     {{driving_url}} {{seed}} {{param.steps}} {{reference_strength}}
2) Применить режимы: POST /admin/modes/reload (Bearer internal-JWT).
3) Слать POST /generate — и всё работает.
Проверка: curl http://localhost:8000/health
DONE
