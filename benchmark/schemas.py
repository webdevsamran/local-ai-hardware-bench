"""Result schema definition and validation.

Every benchmark result written by this framework conforms to schema
version 1.0. Validation is intentionally dependency-free so results can
be validated anywhere (CI, vendor review, offline).
"""

from __future__ import annotations

from typing import Any

SCHEMA_VERSION = "1.0"

# Fields that must be present at the top level of every result document.
_TOP_LEVEL_REQUIRED = ("schema_version", "run_id", "timestamp", "system", "runtime", "model", "metrics")

# Metric fields. A metric that could not be measured MUST be null, never
# an estimate. Types are enforced: numbers must be int/float (bool excluded),
# null is always allowed.
_METRIC_FIELDS: dict[str, tuple[type, ...]] = {
    "load_time_ms": (int, float),
    "ttft_ms": (int, float),
    "prompt_tokens_per_second": (int, float),
    "generation_tokens_per_second": (int, float),
    "total_latency_ms": (int, float),
    "p50_latency_ms": (int, float),
    "p95_latency_ms": (int, float),
    "peak_ram_mb": (int, float),
    "peak_vram_mb": (int, float),
    "avg_cpu_util_percent": (int, float),
    "avg_gpu_util_percent": (int, float),
    "max_temperature_c": (int, float),
    "average_power_watts": (int, float),
    "performance_per_watt": (int, float),
}

_SYSTEM_FIELDS = {
    "os": str,
    "os_version": str,
    "cpu": str,
    "cpu_cores_physical": int,
    "cpu_cores_logical": int,
    "gpu": str,
    "gpu_vram_mb": int,
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
}


def _check_fields(section: dict[str, Any], spec: dict[str, Any], prefix: str, errors: list[str]) -> None:
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

    for field in ("run_id", "timestamp"):
        if field in data and not isinstance(data[field], str):
            errors.append(f"{field}: expected string")

    system = data.get("system")
    if system is not None:
        if not isinstance(system, dict):
            errors.append("system: must be an object")
        else:
            _check_fields(system, _SYSTEM_FIELDS, "system", errors)
            if "ram_gb" in system and system["ram_gb"] is not None and system["ram_gb"] <= 0:
                errors.append("system.ram_gb: must be positive")

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
            _check_fields(metrics, _METRIC_FIELDS, "metrics", errors)

    # Reproducibility block (optional but strongly recommended).
    repro = data.get("reproducibility")
    if repro is not None and not isinstance(repro, dict):
        errors.append("reproducibility: must be an object")

    return errors


def validate_or_raise(data: Any) -> None:
    """Validate a result document, raising ValueError on the first error."""
    errors = validate_result(data)
    if errors:
        raise ValueError("schema validation failed:\n  - " + "\n  - ".join(errors))
