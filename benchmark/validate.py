"""Result validation entry point used by the CLI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .schemas import validate_result


def load_result(path: Path) -> dict[str, Any]:
    """Load a result JSON file."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: top-level JSON must be an object")
    return data


def validate_file(path: Path) -> tuple[bool, list[str]]:
    """Validate a result file. Returns (valid, errors)."""
    try:
        data = load_result(path)
    except (OSError, json.JSONDecodeError) as exc:
        return False, [f"cannot read {path}: {exc}"]
    errors = validate_result(data)
    return len(errors) == 0, errors
