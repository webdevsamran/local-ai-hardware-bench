"""Declarative experiment manifests (#6).

An experiment manifest describes models, runtimes, devices, workloads,
repetitions, telemetry settings, and optional sweeps in YAML, TOML, or
JSON. ``aihwbench run <manifest>`` executes it.

Format support is dependency-aware:
- JSON: always.
- TOML: stdlib ``tomllib`` on Python >= 3.11.
- YAML: optional PyYAML.

Unknown keys are rejected so typos fail loudly instead of silently
changing what is measured.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = ["Experiment", "load_experiment", "ExperimentError"]


class ExperimentError(ValueError):
    """Raised when a manifest is missing required fields or has bad types."""


_ALLOWED_TOP_LEVEL = {
    "name",
    "description",
    "models",
    "model_paths",
    "runtimes",
    "devices",
    "workloads",
    "repetitions",
    "telemetry",
    "sweep",
}


@dataclass(frozen=True)
class Experiment:
    name: str
    models: tuple[str, ...] = ()
    model_paths: tuple[str, ...] = ()
    runtimes: tuple[str, ...] = ()
    devices: tuple[str, ...] = ("auto",)
    workloads: tuple[str, ...] = ("default_chat",)
    repetitions: int = 1
    telemetry_interval_s: float = 0.5
    sweep: dict[str, tuple[Any, ...]] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "models": list(self.models),
            "model_paths": list(self.model_paths),
            "runtimes": list(self.runtimes),
            "devices": list(self.devices),
            "workloads": list(self.workloads),
            "repetitions": self.repetitions,
            "telemetry": {"interval_seconds": self.telemetry_interval_s},
            "sweep": {k: list(v) for k, v in self.sweep.items()},
        }


def _require_str_list(data: dict[str, Any], key: str) -> tuple[str, ...]:
    value = data.get(key)
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (list, tuple)) and all(isinstance(v, str) for v in value):
        return tuple(value)
    raise ExperimentError(f"{key}: expected a string or list of strings")


def _parse(data: Any, source: str) -> Experiment:
    if not isinstance(data, dict):
        raise ExperimentError(f"{source}: top level must be a mapping")
    unknown = set(data) - _ALLOWED_TOP_LEVEL
    if unknown:
        raise ExperimentError(f"{source}: unknown keys {sorted(unknown)}")
    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ExperimentError(f"{source}: 'name' is required and must be a non-empty string")
    repetitions = data.get("repetitions", 1)
    if not isinstance(repetitions, int) or repetitions < 1:
        raise ExperimentError(f"{source}: repetitions must be a positive integer")
    telemetry = data.get("telemetry", {})
    if not isinstance(telemetry, dict):
        raise ExperimentError(f"{source}: telemetry must be a mapping")
    interval = telemetry.get("interval_seconds", 0.5)
    if not isinstance(interval, (int, float)) or interval <= 0:
        raise ExperimentError(f"{source}: telemetry.interval_seconds must be > 0")
    sweep_raw = data.get("sweep", {})
    if not isinstance(sweep_raw, dict):
        raise ExperimentError(f"{source}: sweep must be a mapping of axis -> list")
    sweep: dict[str, tuple[Any, ...]] = {}
    for axis, values in sweep_raw.items():
        if not isinstance(values, list) or not values:
            raise ExperimentError(f"{source}: sweep.{axis} must be a non-empty list")
        sweep[axis] = tuple(values)
    return Experiment(
        name=name,
        models=_require_str_list(data, "models"),
        model_paths=_require_str_list(data, "model_paths"),
        runtimes=_require_str_list(data, "runtimes"),
        devices=_require_str_list(data, "devices") or ("auto",),
        workloads=_require_str_list(data, "workloads") or ("default_chat",),
        repetitions=repetitions,
        telemetry_interval_s=float(interval),
        sweep=sweep,
    )


def load_experiment(path: Path) -> Experiment:
    """Load and validate an experiment manifest (.json/.toml/.yaml/.yml)."""
    suffix = path.suffix.lower()
    text = path.read_text(encoding="utf-8")
    if suffix == ".json":
        return _parse(json.loads(text), str(path))
    if suffix == ".toml":
        try:
            import tomllib
        except ModuleNotFoundError as exc:  # Python 3.10
            raise ExperimentError("TOML manifests require Python >= 3.11 (stdlib tomllib)") from exc
        return _parse(tomllib.loads(text), str(path))
    if suffix in (".yaml", ".yml"):
        try:
            import yaml
        except ModuleNotFoundError as exc:
            raise ExperimentError("YAML manifests require PyYAML: pip install pyyaml") from exc
        return _parse(yaml.safe_load(text), str(path))
    raise ExperimentError(f"unsupported manifest format {suffix!r}; use .json, .toml, or .yaml")
