#!/usr/bin/env bash
set -euo pipefail

STACK_DIR="${STACK_DIR:-/root/ai-generation-api}"
API_HEALTH_URL="${API_HEALTH_URL:-http://localhost:8000/health}"
COMFY_SERVICE_NAME="${COMFY_SERVICE_NAME:-comfyui}"

echo "===> ComfyUI service"
systemctl is-active "${COMFY_SERVICE_NAME}"

echo "===> Docker compose stack"
docker compose -f "${STACK_DIR}/docker-compose.yml" ps

echo "===> API health"
curl -fsS "${API_HEALTH_URL}"
echo

echo "Health checks finished."
