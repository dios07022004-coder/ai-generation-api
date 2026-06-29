#!/usr/bin/env bash
set -euo pipefail

STACK_DIR="${STACK_DIR:-/root/ai-generation-api}"
RESTART_COMFYUI="${RESTART_COMFYUI:-0}"
RELOAD_URL="${RELOAD_URL:-}"
INTERNAL_JWT="${INTERNAL_JWT:-}"

echo "===> Restarting worker"
cd "${STACK_DIR}"
docker compose restart worker

if [[ "${RESTART_COMFYUI}" == "1" ]]; then
  echo "===> Restarting ComfyUI service"
  systemctl restart comfyui
fi

if [[ -n "${RELOAD_URL}" ]]; then
  if [[ -z "${INTERNAL_JWT}" ]]; then
    echo "INTERNAL_JWT is required when RELOAD_URL is set"
    exit 1
  fi
  echo "===> Calling /admin/modes/reload"
  curl -fsS -X POST "${RELOAD_URL}" \
    -H "Authorization: Bearer ${INTERNAL_JWT}" \
    -H "Content-Type: application/json"
  echo
fi

echo "Config apply finished."
