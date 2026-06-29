#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <exported_api_workflow.json>"
  exit 1
fi

SRC_PATH="$1"
DST_PATH="${2:-config/workflows/video_i2v.json}"

if [[ ! -f "${SRC_PATH}" ]]; then
  echo "Source workflow not found: ${SRC_PATH}"
  exit 1
fi

echo "Validating source workflow..."
python3 scripts/ops/validate_video_workflow.py --workflow "${SRC_PATH}"

echo "Installing workflow to ${DST_PATH}"
cp "${SRC_PATH}" "${DST_PATH}"

echo "Done. Next step:"
echo "  bash scripts/ops/apply_config_changes.sh"
