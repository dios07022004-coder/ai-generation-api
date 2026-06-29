#!/usr/bin/env bash
set -euo pipefail

# Downloads model files listed in a TSV manifest:
# target_subdir<TAB>url<TAB>expected_size_bytes(optional)
#
# Example:
# diffusion_models<TAB>https://example.com/wan.safetensors<TAB>15432123456

COMFY_MODELS_ROOT="${COMFY_MODELS_ROOT:-/root/ComfyUI/models}"
MANIFEST_PATH="${1:-}"

if [[ -z "${MANIFEST_PATH}" ]]; then
  echo "Usage: $0 <manifest.tsv>"
  echo "Optional env: COMFY_MODELS_ROOT=/root/ComfyUI/models"
  exit 1
fi

if [[ ! -f "${MANIFEST_PATH}" ]]; then
  echo "Manifest not found: ${MANIFEST_PATH}"
  exit 1
fi

ensure_dir() {
  local target_dir="$1"
  if [[ ! -d "${target_dir}" ]]; then
    echo "Creating directory: ${target_dir}"
    mkdir -p "${target_dir}"
  fi
}

download_file() {
  local target_subdir="$1"
  local url="$2"
  local expected_size="${3:-}"
  local target_dir="${COMFY_MODELS_ROOT}/${target_subdir}"

  ensure_dir "${target_dir}"

  echo "Downloading: ${url}"
  wget -c -P "${target_dir}" "${url}"

  local file_name
  file_name="$(basename "${url%%\?*}")"
  local target_path="${target_dir}/${file_name}"

  if [[ ! -f "${target_path}" ]]; then
    echo "Downloaded file not found: ${target_path}"
    exit 1
  fi

  if [[ -n "${expected_size}" ]]; then
    local actual_size
    actual_size="$(stat -c '%s' "${target_path}")"
    if [[ "${actual_size}" != "${expected_size}" ]]; then
      echo "Size mismatch for ${target_path}: expected=${expected_size}, actual=${actual_size}"
      exit 1
    fi
  fi

  ls -lah "${target_path}"
}

while IFS=$'\t' read -r target_subdir url expected_size || [[ -n "${target_subdir:-}" ]]; do
  [[ -z "${target_subdir}" ]] && continue
  [[ "${target_subdir:0:1}" == "#" ]] && continue

  if [[ -z "${url:-}" ]]; then
    echo "Invalid line in manifest (missing URL): ${target_subdir}"
    exit 1
  fi

  download_file "${target_subdir}" "${url}" "${expected_size:-}"
done < "${MANIFEST_PATH}"

echo "All manifest entries processed successfully."
