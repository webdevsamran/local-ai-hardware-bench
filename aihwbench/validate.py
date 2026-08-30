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


def validate_file(path: Path, formal: bool = False) -> tuple[bool, list[str]]:
    """Validate a result file. Returns (valid, errors).

    With ``formal=True`` the versioned JSON Schema from
    :mod:`aihwbench.formal_schema` is also applied (#22). Formal
    validation fails closed: when the optional ``jsonschema`` dependency
    is missing, an explicit error is returned instead of a silent pass.
    """
    try:
        data = load_result(path)
    except (OSError, json.JSONDecodeError) as exc:
        return False, [f"cannot read {path}: {exc}"]
    errors = validate_result(data)
    if formal:
        try:
            from .formal_schema import validate_formal

            errors = errors + validate_formal(data)
        except RuntimeError as exc:
            errors = errors + [f"formal validation unavailable: {exc}"]
    return len(errors) == 0, errors
