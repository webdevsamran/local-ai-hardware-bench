"""Comparison safety classification.

Classifies whether two benchmark results are safe to compare:

- STRICTLY_COMPARABLE: all materially relevant dimensions match.
- CONDITIONALLY_COMPARABLE: model/workload match but caveats exist.
- NOT_COMPARABLE: direct metric comparison would be misleading.

Never decides winners; only decides whether a comparison is safe.
Machine-readable reasons are included for automation/CI.
"""

from __future__ import annotations

from typing import Any

STRICTLY_COMPARABLE = "STRICTLY_COMPARABLE"
CONDITIONALLY_COMPARABLE = "CONDITIONALLY_COMPARABLE"
NOT_COMPARABLE = "NOT_COMPARABLE"

# Differing strictly => NOT_COMPARABLE.
_STRICT = (
    "model.name",
    "model.checksum",
    "model.format",
    "model.quantization",
    "model.revision",
    "model.tokenizer",
    "runtime.name",
    "runtime.backend",
    "runtime.device",
    "reproducibility.workload_type",
    "reproducibility.prompt",
    "reproducibility.max_tokens",
    "reproducibility.temperature",
    "reproducibility.seed",
    "reproducibility.context_length",
    "reproducibility.batch_size",
    "reproducibility.concurrency",
    "reproducibility.warmup_runs",
    "reproducibility.iterations",
)

# Differing these => CONDITIONALLY_COMPARABLE.
_CONDITIONAL = (
    "reproducibility.power_profile",
    "system.os_version",
    "runtime.version",
)


def _get(a: dict[str, Any], path: str) -> Any:
    value: Any = a
    for part in path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
        if value is None:
            return None
    return value


def _same(a: Any, b: Any) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return bool(a == b)


def comparability_warnings(a: dict[str, Any], b: dict[str, Any]) -> list[str]:
    """Human-readable warnings when results are not strictly comparable."""
    reasons: list[str] = compare_classification(a, b)["reasons"]
    return reasons


def compare_classification(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """Classify comparability of two result documents.

    Returns dict with "classification", "reasons" (human), and
    "machine_reasons" (stable dotted keys).
    """
    reasons: list[str] = []
    machine: list[str] = []

    strict_diffs = [p for p in _STRICT if not _same(_get(a, p), _get(b, p))]
    conditional_diffs = [p for p in _CONDITIONAL if not _same(_get(a, p), _get(b, p))]

    for path in strict_diffs:
        if _get(a, path) is None and _get(b, path) is None:
            continue
        va, vb = _get(a, path), _get(b, path)
        if path == "model.name":
            reasons.append(f"models differ: {va!r} vs {vb!r}")
        else:
            reasons.append(f"{path}: {va!r} vs {vb!r}")
        machine.append(path)

    for path in conditional_diffs:
        if _get(a, path) is None and _get(b, path) is None:
            continue
        reasons.append(
            f"{path} differs ({_get(a, path)!r} vs {_get(b, path)!r}) - interpret as conditional"
        )
        machine.append(path)

    if _get(a, "system.cpu") != _get(b, "system.cpu") or _get(a, "system.gpu") != _get(
        b, "system.gpu"
    ):
        reasons.append("hardware differs between results - treat as cross-platform reference only")
        machine.append("system.hardware")

    if strict_diffs:
        classification = NOT_COMPARABLE
    elif machine:
        classification = CONDITIONALLY_COMPARABLE
    else:
        classification = STRICTLY_COMPARABLE

    return {
        "classification": classification,
        "reasons": reasons,
        "machine_reasons": sorted(set(machine)),
    }


def assert_comparable(a: dict[str, Any], b: dict[str, Any]) -> None:
    """Raise ValueError when two results are NOT_COMPARABLE."""
    result = compare_classification(a, b)
    if result["classification"] == NOT_COMPARABLE:
        detail = "\n  - ".join(result["reasons"])
        raise ValueError("Results are NOT_COMPARABLE:\n  - " + detail)
