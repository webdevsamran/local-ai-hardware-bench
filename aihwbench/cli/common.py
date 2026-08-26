"""Shared helpers for aihwbench CLI command modules."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def echo_json(data: object) -> None:
    """Print an object as pretty-printed JSON."""
    print(json.dumps(data, indent=2, default=str))


def fail(message: str) -> None:
    """Print an actionable error to stderr."""
    print(f"ERROR: {message}", file=sys.stderr)


def load_results_dir(results_dir: Path) -> list[dict]:
    """Load every parseable result JSON in a directory (skips bad files)."""
    results = []
    for path in sorted(results_dir.glob("*.json")):
        try:
            results.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    return results
