#!/usr/bin/env python3
"""Validate and smoke-check VIDEO_VARIATION_1..40 modes."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any
from urllib import error, request

import yaml

ANCHOR_FACE = "Keep the SAME face and identity across ALL frames"
ANCHOR_SCENE = "Keep the SAME location and background as in the source image"
ANCHOR_METADATA = "{{ metadata.change | default('') }}"


def load_yaml(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain YAML object")
    return data


def validate_files(modes_dir: Path) -> list[str]:
    errors: list[str] = []
    mode_files = [modes_dir / f"VIDEO_VARIATION_{i}.yaml" for i in range(1, 41)]

    for path in mode_files:
        if not path.exists():
            errors.append(f"Missing mode file: {path}")
            continue

        data = load_yaml(path)
        mode_id = data.get("id")
        expected_id = path.stem
        if mode_id != expected_id:
            errors.append(f"{path}: id must be '{expected_id}', got '{mode_id}'")

        if data.get("type") != "video":
            errors.append(f"{path}: type must be 'video'")
        if data.get("enabled") is not True:
            errors.append(f"{path}: enabled must be true")
        if data.get("model") != "video_generation_model":
            errors.append(f"{path}: model must be 'video_generation_model'")
        if data.get("workflow") != "video_i2v":
            errors.append(f"{path}: workflow must be 'video_i2v'")

        params = data.get("params", {})
        for key in ("width", "height", "num_frames", "fps", "steps", "cfg"):
            if key not in params:
                errors.append(f"{path}: params.{key} is required")

        prompt = str(data.get("prompt_template", ""))
        if ANCHOR_FACE not in prompt:
            errors.append(f"{path}: missing identity anchor")
        if ANCHOR_SCENE not in prompt:
            errors.append(f"{path}: missing scene anchor")
        if ANCHOR_METADATA not in prompt:
            errors.append(f"{path}: missing metadata.change insertion")

    return errors


def _api_request(url: str, method: str, payload: dict[str, Any], api_key: str) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url,
        data=body,
        method=method,
        headers={"Content-Type": "application/json", "X-API-Key": api_key},
    )
    with request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def run_preview_checks(base_url: str, api_key: str, image_url: str) -> list[str]:
    errors: list[str] = []
    for i in range(1, 41):
        mode_id = f"VIDEO_VARIATION_{i}"
        url = f"{base_url}/modes/{mode_id}/preview"
        payload = {"image_url": image_url, "metadata": {"change": "natural motion"}}
        try:
            result = _api_request(url, "POST", payload, api_key)
        except error.HTTPError as exc:
            errors.append(f"{mode_id}: preview HTTP {exc.code}")
            continue
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{mode_id}: preview failed: {exc}")
            continue

        if not result.get("prompt"):
            errors.append(f"{mode_id}: preview returned empty prompt")
    return errors


def run_smoke_checks(base_url: str, api_key: str, image_url: str, wait_seconds: int) -> list[str]:
    errors: list[str] = []
    for i in range(1, 41):
        mode_id = f"VIDEO_VARIATION_{i}"
        create_url = f"{base_url}/generate"
        create_payload = {
            "task_type": "video",
            "mode": mode_id,
            "image_url": image_url,
            "metadata": {"change": "natural motion"},
        }
        try:
            created = _api_request(create_url, "POST", create_payload, api_key)
        except error.HTTPError as exc:
            errors.append(f"{mode_id}: generate HTTP {exc.code}")
            continue
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{mode_id}: generate failed: {exc}")
            continue

        task_id = created.get("task_id")
        if not task_id:
            errors.append(f"{mode_id}: no task_id in response")
            continue

        task_url = f"{base_url}/tasks/{task_id}"
        deadline = time.time() + wait_seconds
        while time.time() < deadline:
            try:
                req = request.Request(task_url, headers={"X-API-Key": api_key})
                with request.urlopen(req, timeout=30) as resp:
                    task = json.loads(resp.read().decode("utf-8"))
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{mode_id}: task poll failed: {exc}")
                break

            status = task.get("status")
            if status in {"completed", "failed"}:
                if status == "failed":
                    errors.append(f"{mode_id}: task failed ({task.get('error')})")
                break
            time.sleep(3)
        else:
            errors.append(f"{mode_id}: timeout waiting task completion ({task_id})")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate and smoke-check VIDEO_VARIATION_1..40.")
    parser.add_argument(
        "--modes-dir",
        default="config/modes/video",
        help="Path to video modes directory.",
    )
    parser.add_argument("--api-base-url", help="Optional API base URL (e.g. http://localhost:8000)")
    parser.add_argument("--api-key", help="API key for preview/smoke checks")
    parser.add_argument("--image-url", help="Test image URL for preview/smoke checks")
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Run generate + task polling for each mode (expensive).",
    )
    parser.add_argument(
        "--smoke-timeout-seconds",
        type=int,
        default=180,
        help="Max wait for each smoke task.",
    )
    args = parser.parse_args()

    errors = validate_files(Path(args.modes_dir))
    if errors:
        print("File validation failed:")
        for line in errors:
            print(f"  - {line}")
        return 1
    print("File validation passed for VIDEO_VARIATION_1..40")

    if args.api_base_url:
        if not args.api_key or not args.image_url:
            print("--api-base-url requires --api-key and --image-url")
            return 1

        preview_errors = run_preview_checks(args.api_base_url, args.api_key, args.image_url)
        if preview_errors:
            print("Preview validation failed:")
            for line in preview_errors:
                print(f"  - {line}")
            return 1
        print("Preview validation passed for VIDEO_VARIATION_1..40")

        if args.smoke:
            smoke_errors = run_smoke_checks(
                args.api_base_url,
                args.api_key,
                args.image_url,
                args.smoke_timeout_seconds,
            )
            if smoke_errors:
                print("Smoke validation failed:")
                for line in smoke_errors:
                    print(f"  - {line}")
                return 1
            print("Smoke validation passed for VIDEO_VARIATION_1..40")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
