"""Benchmark runner — orchestrates a full benchmark execution."""

from __future__ import annotations

import json
import platform
import subprocess
import uuid
from pathlib import Path
from typing import Any

from .schemas import validate_or_raise


def git_commit() -> str | None:
    """Current git commit hash of this repository, if available."""
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5.0,
            encoding="utf-8", errors="replace",
        )
        if proc.returncode == 0:
            return proc.stdout.strip()
    except OSError:
        pass
    return None


def power_profile() -> str | None:
    """Windows power scheme name (reproducibility metadata)."""
    if platform.system() != "Windows":
        return None
    try:
        proc = subprocess.run(
            ["powercfg", "/getactivescheme"],
            capture_output=True, text=True, timeout=5.0,
            encoding="utf-8", errors="replace",
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip().splitlines()[-1]
    except OSError:
        pass
    return None


def run_benchmark(runtime: str, config: Any) -> dict[str, Any]:
    """Run one benchmark end-to-end and return a validated result document."""
    from .backends import resolve
    from .system_info import detect_system

    backend = resolve(runtime)
    system = detect_system()

    result = backend.run(config, system)

    # Enrich with environment/reproducibility metadata.
    result.setdefault("run_id", f"{runtime}-{uuid.uuid4().hex[:8]}")
    result["git_commit"] = git_commit()
    repro = result.setdefault("reproducibility", {})
    repro.setdefault("python_version", platform.python_version())
    repro.setdefault("power_profile", power_profile())

    validate_or_raise(result)
    return result


def save_result(result: dict[str, Any], directory: Path) -> Path:
    """Write a result document to a results directory."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{result['run_id']}.json"
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return path
