"""Data-quality scoring, invalidation, and anomaly review (#42, #43, #44).

- ``data_quality_report``: machine-readable checks per result (schema,
  privacy, provenance, reproducibility completeness, variance, outliers,
  trust state).
- ``invalidate_result``: wraps a result in an invalidation record — bad
  history is never silently deleted; it is superseded with a reason and a
  replacement reference.
- ``flag_anomalies``: statistically suspicious results are flagged for
  human review. Flags are review requests, never fraud verdicts.
"""

from __future__ import annotations

import re
from typing import Any

from .repro import reproducibility_score
from .schemas import validate_result
from .stats import summarize

__all__ = [
    "data_quality_report",
    "invalidate_result",
    "flag_anomalies",
    "TRUST_STATES",
]

TRUST_STATES = ("unreviewed", "verified", "flagged", "invalidated", "superseded")

# Patterns that must never appear in published results (privacy scan).
# Backslashes are built via chr(92) so the patterns stay readable and
# shell/tooling safe.
_BS = chr(92)  # one backslash character
_DQ = chr(34)  # one double-quote character

_PRIVACY_PATTERNS = {
    # Windows user profile paths: C:\Users\<name>\...
    # Regex needs literal backslashes, so each path separator is two
    # backslash characters (_BS + _BS).
    # One-or-more backslashes so both raw strings and repr() output
    # (which doubles backslashes) are matched.
    # Each path separator in regex is an escaped backslash followed by a
    # one-or-more quantifier (_BS + _BS + "+").
    "windows_path": re.compile(
        "[A-Za-z]:" + _BS + _BS + "+Users" + _BS + _BS + "+[^" + _DQ + _BS + _BS + "]+"
    ),
    "home_path": re.compile("/home/[a-z0-9_-]+", re.IGNORECASE),
    "mac_address": re.compile("([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}"),
    "email": re.compile("[^@" + _BS + "s]+@[^@" + _BS + "s]+"),
    "serial_like": re.compile("SN[-:]?" + _BS + "s?[0-9A-Z]{8,}"),
}


def _privacy_scan(result: dict[str, Any]) -> list[str]:
    text = repr(result)
    return [name for name, pattern in _PRIVACY_PATTERNS.items() if pattern.search(text)]


def data_quality_report(result: dict[str, Any]) -> dict[str, Any]:
    """Machine-readable quality checks for one result document."""
    schema_errors = validate_result(result)
    privacy_hits = _privacy_scan(result)
    repro = reproducibility_score(result)

    iterations = result.get("iterations") or []
    latencies = [
        i.get("total_latency_ms")
        for i in iterations
        if isinstance(i, dict) and i.get("total_latency_ms") is not None
    ]
    variance = summarize(latencies) if latencies else None
    high_variance = bool(variance and variance["cv"] is not None and variance["cv"] > 0.5)

    trust = result.get("trust_state", "unreviewed")
    if trust not in TRUST_STATES:
        trust = "unreviewed"

    checks = {
        "schema_valid": not schema_errors,
        "schema_errors": schema_errors,
        "privacy_clean": not privacy_hits,
        "privacy_hits": privacy_hits,
        "provenance_present": bool((result.get("provenance") or {}).get("result_hash")),
        "reproducibility_score": repro["score"],
        "variance_acceptable": not high_variance,
        "cv_latency": variance["cv"] if variance else None,
        "trust_state": trust,
    }
    passed = sum(
        1
        for key in ("schema_valid", "privacy_clean", "provenance_present", "variance_acceptable")
        if checks[key]
    )
    return {"checks": checks, "checks_passed": passed, "checks_total": 4}


def invalidate_result(
    result: dict[str, Any],
    reason: str,
    replacement_run_id: str | None = None,
    invalidated_by: str = "maintainer",
) -> dict[str, Any]:
    """Produce an invalidation record; the original result is preserved."""
    if not reason or not reason.strip():
        raise ValueError("invalidation requires a non-empty reason")
    record = {
        "invalidated_run_id": result.get("run_id"),
        "reason": reason.strip(),
        "replacement_run_id": replacement_run_id,
        "invalidated_by": invalidated_by,
        "original_result": result,
        "note": (
            "the original result is retained verbatim; consumers must treat "
            "it as superseded, not deleted"
        ),
    }
    return record


def flag_anomalies(
    results: list[dict[str, Any]],
    metric: str = "generation_tokens_per_second",
    z_threshold: float = 3.0,
) -> list[dict[str, Any]]:
    """Flag results whose metric deviates > z_threshold sigma from the group.

    Flags request human review; they never assert fraud and never remove
    results automatically.
    """
    values = [(r.get("run_id"), (r.get("metrics") or {}).get(metric)) for r in results]
    measured = [v for _, v in values if v is not None]
    if len(measured) < 3:
        return []  # too little data to say anything statistical
    mean = sum(measured) / len(measured)
    variance = sum((v - mean) ** 2 for v in measured) / (len(measured) - 1)
    stddev = variance**0.5
    if stddev == 0:
        return []
    flags: list[dict[str, Any]] = []
    for run_id, value in values:
        if value is None:
            continue
        z = (value - mean) / stddev
        if abs(z) > z_threshold:
            flags.append(
                {
                    "run_id": run_id,
                    "metric": metric,
                    "value": value,
                    "z_score": round(z, 3),
                    "group_mean": round(mean, 3),
                    "group_stddev": round(stddev, 3),
                    "action": "manual_review",
                }
            )
    return flags
