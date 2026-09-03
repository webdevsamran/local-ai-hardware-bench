"""Benchmark suite loading and execution.

A suite is a versioned JSON profile under ``configs/suites/`` that pins
every reproducibility-relevant parameter: prompt, token budget, sampling,
context length, warmups, iterations, and model tier. Suites make results
comparable across machines and time.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .backends import BenchmarkConfig, resolve
from .runner import run_benchmark, save_result

SUITES_DIR = Path(__file__).resolve().parent.parent / "configs" / "suites"


def list_suites() -> list[str]:
    """Names of available suite profiles."""
    return sorted(p.stem for p in SUITES_DIR.glob("*.json"))


def load_suite(name: str) -> dict[str, Any]:
    """Load a suite profile by name. Raises FileNotFoundError if missing."""
    path = SUITES_DIR / f"{name}.json"
    if not path.is_file():
        raise FileNotFoundError(f"suite {name!r} not found. Available: {', '.join(list_suites())}")
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def suite_config(suite: dict[str, Any], runtime: str, model: str | None) -> BenchmarkConfig:
    """Build a BenchmarkConfig from a suite profile."""
    workload = suite["workload"]
    return BenchmarkConfig(
        model=model or "",
        prompt=workload["prompt"],
        max_tokens=workload["max_tokens"],
        warmup_runs=workload.get("warmup_runs", 2),
        iterations=workload.get("iterations", 5),
        temperature=workload.get("temperature", 0.0),
        seed=workload.get("seed", 42),
        context_length=workload.get("context_length", 2048),
        device=workload.get("device", "auto"),
        extra={"model_path": model, "suite": suite["name"]},
    )


def run_suite(
    name: str,
    runtime: str,
    model: str | None,
    output_dir: Path,
) -> list[Path]:
    """Run one suite profile against one runtime. Returns saved result paths."""
    suite = load_suite(name)
    resolve(runtime)  # raises BackendError for unknown runtime
    config = suite_config(suite, runtime, model)
    result = run_benchmark(runtime, config)
    result.setdefault("reproducibility", {})["suite"] = name
    path = save_result(result, output_dir / "raw")
    return [path]
