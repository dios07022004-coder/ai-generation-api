#!/usr/bin/env python3
"""Validate exported ComfyUI video workflow before wiring to API modes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

REQUIRED_PLACEHOLDERS = (
    "{{prompt}}",
    "{{negative}}",
    "{{seed}}",
    "{{param.steps}}",
    "{{param.cfg}}",
    "{{param.width}}",
    "{{param.height}}",
    "{{param.num_frames}}",
    "{{param.fps}}",
)

RECOMMENDED_PLACEHOLDERS = (
    "{{model.name}}",
    "{{image_name}}",
    "{{image_url}}",
)


def _flatten(node: object) -> str:
    return json.dumps(node, ensure_ascii=False, separators=(",", ":"))


def validate(path: Path) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    if not path.exists():
        return [f"Workflow file not found: {path}"], warnings

    raw = path.read_text(encoding="utf-8")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        return [f"Invalid JSON: {exc}"], warnings

    if not isinstance(parsed, dict):
        errors.append("Workflow root must be a JSON object")
        return errors, warnings

    if "_comment" in parsed and "ЗАГЛУШКА" in str(parsed.get("_comment")):
        errors.append("Workflow still contains placeholder marker 'ЗАГЛУШКА'")

    packed = _flatten(parsed)
    for token in REQUIRED_PLACEHOLDERS:
        if token not in packed:
            errors.append(f"Missing required placeholder: {token}")

    if "{{image_name}}" not in packed and "{{image_url}}" not in packed:
        errors.append("Workflow must reference either {{image_name}} or {{image_url}}")

    for token in RECOMMENDED_PLACEHOLDERS:
        if token not in packed:
            warnings.append(f"Recommended placeholder not found: {token}")

    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate ComfyUI API-format workflow for video_i2v wiring."
    )
    parser.add_argument(
        "--workflow",
        default="config/workflows/video_i2v.json",
        help="Path to workflow json (default: config/workflows/video_i2v.json)",
    )
    args = parser.parse_args()
    workflow_path = Path(args.workflow)

    errors, warnings = validate(workflow_path)
    if warnings:
        print("Warnings:")
        for line in warnings:
            print(f"  - {line}")

    if errors:
        print("Validation failed:")
        for line in errors:
            print(f"  - {line}")
        return 1

    print(f"Workflow validation passed: {workflow_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
