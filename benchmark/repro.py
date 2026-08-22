"""Reproducibility tooling (#33, #34, #35).

- ``env_diff``: field-by-field comparison of two result documents.
- ``reproducibility_score``: transparent metadata-completeness score.
  It measures how much information a result carries for reproduction —
  it is explicitly NOT a measure of scientific validity.
- ``check_reproduction``: validates prerequisites for rerunning a result
  and reports deviations between stored and current environment.
"""

from __future__ import annotations

import platform
from typing import Any

__all__ = ["env_diff", "reproducibility_score", "check_reproduction"]

# Fields compared by env-diff, grouped for readable output.
_DIFF_FIELDS = {
    "system": (
        "os",
        "os_version",
        "cpu",
        "cpu_cores_physical",
        "gpu",
        "gpu_vram_mb",
        "npu",
        "ram_gb",
    ),
    "runtime": ("name", "version", "backend", "device"),
    "model": ("name", "format", "quantization", "revision"),
    "reproducibility": (
        "prompt",
        "max_tokens",
        "temperature",
        "seed",
        "context_length",
        "iterations",
    ),
}


def _flatten(doc: dict[str, Any]) -> dict[str, Any]:
    flat: dict[str, Any] = {}
    for section, fields in _DIFF_FIELDS.items():
        sub = doc.get(section) or {}
        for f in fields:
            flat[f"{section}.{f}"] = sub.get(f)
    return flat


def env_diff(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """Matching and differing environment/model/workload fields."""
    fa, fb = _flatten(a), _flatten(b)
    matching = {k: v for k, v in fa.items() if v == fb.get(k)}
    differing = {k: {"a": v, "b": fb.get(k)} for k, v in fa.items() if v != fb.get(k)}
    return {"matching": matching, "differing": differing}


def reproducibility_score(result: dict[str, Any]) -> dict[str, Any]:
    """Metadata-completeness score in [0, 1] with per-item detail.

    Each checked item contributes equally. Missing optional metadata
    lowers the score; nothing is inferred or fabricated to fill gaps.
    """
    items = {
        "model_checksum": bool((result.get("model") or {}).get("checksum")),
        "runtime_version": bool((result.get("runtime") or {}).get("version")),
        "workload_identity": bool(result.get("workload")),
        "seed": (result.get("reproducibility") or {}).get("seed") is not None,
        "power_profile": bool((result.get("reproducibility") or {}).get("power_profile")),
        "tokenizer": bool((result.get("model") or {}).get("tokenizer")),
        "git_commit": bool(result.get("git_commit")),
        "command": bool((result.get("reproducibility") or {}).get("command")),
        "python_version": bool((result.get("reproducibility") or {}).get("python_version")),
        "provenance_hash": bool((result.get("provenance") or {}).get("result_hash")),
    }
    total = len(items)
    present = sum(1 for ok in items.values() if ok)
    return {
        "score": round(present / total, 3),
        "present": present,
        "total": total,
        "items": items,
        "note": (
            "metadata-completeness only; this score says nothing about "
            "whether the measurement itself is scientifically valid"
        ),
    }


def check_reproduction(
    result: dict[str, Any],
    current_system: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Report whether a result can be reproduced on this machine.

    Checks model checksum availability, runtime presence, and environment
    deviations against the optionally supplied current system snapshot.
    """
    system = current_system or {}
    runtime_name = (result.get("runtime") or {}).get("name")
    deviations = env_diff(result, {"system": system})["differing"]
    blockers: list[str] = []
    if not (result.get("model") or {}).get("checksum"):
        blockers.append("model checksum missing from result")
    if not runtime_name:
        blockers.append("runtime name missing from result")
    return {
        "run_id": result.get("run_id"),
        "can_attempt": not blockers,
        "blockers": blockers,
        "environment_deviations": list(deviations),
        "current_platform": platform.system(),
        "note": (
            "deviations do not block reproduction by themselves but are "
            "reported so the operator can judge comparability"
        ),
    }
