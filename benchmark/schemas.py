"""Result schema definition and validation.

Every benchmark result written by this framework conforms to schema
version 1.0. Validation is intentionally dependency-free so results can
be validated anywhere (CI, vendor review, offline).
"""

from __future__ import annotations

import re
from typing import Any

SCHEMA_VERSION = "1.0"

# Fields that must be present at the top level of every result document.
_TOP_LEVEL_REQUIRED = (
    "schema_version",
    "run_id",
    "timestamp",
    "system",
    "runtime",
    "model",
    "metrics",
)

_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

# Metric fields. A metric that could not be measured MUST be null, never
# an estimate. Types are enforced: numbers must be int/float (bool excluded),
# null is always allowed.
#
# Each entry is (type_tuple, minimum, maximum). None means unbounded.
_METRIC_FIELDS: dict[str, tuple[tuple[type, ...], float | None, float | None]] = {
    "load_time_ms": ((int, float), 0.0, None),
    "ttft_ms": ((int, float), 0.0, None),
    "prompt_tokens_per_second": ((int, float), 0.0, None),
    "generation_tokens_per_second": ((int, float), 0.0, None),
    "total_latency_ms": ((int, float), 0.0, None),
    "p50_latency_ms": ((int, float), 0.0, None),
    "p90_latency_ms": ((int, float), 0.0, None),
    "p95_latency_ms": ((int, float), 0.0, None),
    "p99_latency_ms": ((int, float), 0.0, None),
    "peak_ram_mb": ((int, float), 0.0, None),
    "peak_vram_mb": ((int, float), 0.0, None),
    "avg_cpu_util_percent": ((int, float), 0.0, 100.0),
    "avg_gpu_util_percent": ((int, float), 0.0, 100.0),
    "max_temperature_c": ((int, float), 0.0, None),
    "average_power_watts": ((int, float), 0.0, None),
    "performance_per_watt": ((int, float), 0.0, None),
    "throughput_inferences_per_second": ((int, float), 0.0, None),
    "energy_joules_per_token": ((int, float), 0.0, None),
}

_SYSTEM_FIELDS = {
    "os": str,
    "os_version": str,
    "cpu": str,
    "cpu_cores_physical": int,
    "cpu_cores_logical": int,
    "gpu": str,
    "gpu_vram_mb": int,
    "gpu_driver_version": str,
    "npu": str,
    "ram_gb": (int, float),
    "platform_name": str,
}

_RUNTIME_FIELDS = {
    "name": str,
    "version": str,
    "backend": str,
    "device": str,
}

_MODEL_FIELDS = {
    "name": str,
    "format": str,
    "quantization": str,
    "parameters": str,
    "checksum": str,
    "revision": str,
    "tokenizer": str,
}

_REPRO_FIELDS = {
    "prompt": (str, type(None)),
    "max_tokens": (int, type(None)),
    "temperature": (float, int, type(None)),
    "seed": (int, type(None)),
    "context_length": (int, type(None)),
    "warmup_runs": (int, type(None)),
    "iterations": (int, type(None)),
    "command": (str, type(None)),
    "python_version": (str, type(None)),
    "power_profile": (str, type(None)),
    "workload_type": (str, type(None)),
    "batch_size": (int, type(None)),
    "concurrency": (int, type(None)),
}


def _check_fields(
    section: dict[str, Any], spec: dict[str, Any], prefix: str, errors: list[str]
) -> None:
    for key, expected in spec.items():
        if key not in section:
            continue  # optional fields may be omitted; present fields must be valid
        value = section[key]
        if value is None:
            continue
        types = expected if isinstance(expected, tuple) else (expected,)
        if isinstance(value, bool) and bool not in types:
            errors.append(f"{prefix}.{key}: bool is not a valid type")
        elif not isinstance(value, types):
            got = type(value).__name__
            want = "/".join(t.__name__ for t in types)
            errors.append(f"{prefix}.{key}: expected {want}, got {got}")


def _check_metric(
    value: Any,
    prefix: str,
    errors: list[str],
    minimum: float | None = None,
    maximum: float | None = None,
) -> None:
    """Append an error when a numeric value is out of allowed bounds."""
    if isinstance(value, bool):
        errors.append(f"{prefix}: bool is not a valid number")
        return
    if not isinstance(value, (int, float)):
        return  # type errors handled separately in _check_fields
    if minimum is not None and value < minimum:
        errors.append(f"{prefix}: must be >= {minimum:g}, got {value}")
    if maximum is not None and value > maximum:
        errors.append(f"{prefix}: must be <= {maximum:g}, got {value}")


def validate_result(data: Any) -> list[str]:
    """Validate a benchmark result document against schema 1.0.

    Returns a list of human-readable error strings. An empty list means
    the document is valid.
    """
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["result: top-level document must be a JSON object"]

    for field in _TOP_LEVEL_REQUIRED:
        if field not in data:
            errors.append(f"missing required field: {field}")

    if "schema_version" in data and data["schema_version"] != SCHEMA_VERSION:
        errors.append(
            f"schema_version: expected {SCHEMA_VERSION!r}, got {data['schema_version']!r}"
        )

    if "run_id" in data and not isinstance(data["run_id"], str):
        errors.append("run_id: expected string")
    elif "run_id" in data and not _RUN_ID_RE.match(data["run_id"]):
        errors.append("run_id: must match [A-Za-z0-9][A-Za-z0-9._-]{0,127} (no spaces or slashes)")

    if "timestamp" in data and not isinstance(data["timestamp"], str):
        errors.append("timestamp: expected string")
    elif "timestamp" in data and not _TIMESTAMP_RE.match(data["timestamp"]):
        errors.append(
            "timestamp: must be an ISO-8601 UTC timestamp "
            "(YYYY-MM-DDTHH:MM:SSZ), got "
            f"{data['timestamp']!r}"
        )

    system = data.get("system")
    if system is not None:
        if not isinstance(system, dict):
            errors.append("system: must be an object")
        else:
            _check_fields(system, _SYSTEM_FIELDS, "system", errors)
            if "ram_gb" in system and system["ram_gb"] is not None:
                _check_metric(system["ram_gb"], "system.ram_gb", errors, minimum=0.0)
            for key in ("cpu_cores_physical", "cpu_cores_logical"):
                if key in system and system[key] is not None:
                    _check_metric(system[key], f"system.{key}", errors, minimum=1)
            if "gpu_vram_mb" in system and system["gpu_vram_mb"] is not None:
                _check_metric(system["gpu_vram_mb"], "system.gpu_vram_mb", errors, minimum=1)

    runtime = data.get("runtime")
    if runtime is not None:
        if not isinstance(runtime, dict):
            errors.append("runtime: must be an object")
        else:
            _check_fields(runtime, _RUNTIME_FIELDS, "runtime", errors)

    model = data.get("model")
    if model is not None:
        if not isinstance(model, dict):
            errors.append("model: must be an object")
        else:
            _check_fields(model, _MODEL_FIELDS, "model", errors)

    metrics = data.get("metrics")
    if metrics is not None:
        if not isinstance(metrics, dict):
            errors.append("metrics: must be an object")
        else:
            for key, (types, minimum, maximum) in _METRIC_FIELDS.items():
                if key not in metrics:
                    continue
                value = metrics[key]
                if value is None:
                    continue
                if isinstance(value, bool):
                    errors.append(f"metrics.{key}: bool is not a valid type")
                    continue
                if not isinstance(value, types):
                    got = type(value).__name__
                    want = "/".join(t.__name__ for t in types)
                    errors.append(f"metrics.{key}: expected {want}, got {got}")
                    continue
                _check_metric(value, f"metrics.{key}", errors, minimum, maximum)

    # Reproducibility block (optional but strongly recommended).
    repro = data.get("reproducibility")
    if repro is not None:
        if not isinstance(repro, dict):
            errors.append("reproducibility: must be an object")
        else:
            _check_fields(repro, _REPRO_FIELDS, "reproducibility", errors)
            for key in ("max_tokens", "warmup_runs", "iterations"):
                if key in repro and repro[key] is not None:
                    _check_metric(repro[key], f"reproducibility.{key}", errors, minimum=0)
            if "context_length" in repro and repro["context_length"] is not None:
                _check_metric(
                    repro["context_length"],
                    "reproducibility.context_length",
                    errors,
                    minimum=1,
                )
            if "temperature" in repro and repro["temperature"] is not None:
                _check_metric(
                    repro["temperature"],
                    "reproducibility.temperature",
                    errors,
                    minimum=0,
                )
            if "batch_size" in repro and repro["batch_size"] is not None:
                _check_metric(repro["batch_size"], "reproducibility.batch_size", errors, minimum=1)
            if "concurrency" in repro and repro["concurrency"] is not None:
                _check_metric(
                    repro["concurrency"],
                    "reproducibility.concurrency",
                    errors,
                    minimum=1,
                )

    # Optional iterations list: each element must be an object.
    iterations = data.get("iterations")
    if iterations is not None:
        if not isinstance(iterations, list):
            errors.append("iterations: must be an array or null")
        else:
            for i, item in enumerate(iterations):
                if not isinstance(item, dict):
                    errors.append(f"iterations[{i}]: must be an object")

    return errors


def validate_or_raise(data: Any) -> None:
    """Validate a result document, raising ValueError on the first error."""
    errors = validate_result(data)
    if errors:
        raise ValueError("schema validation failed:\n  - " + "\n  - ".join(errors))
