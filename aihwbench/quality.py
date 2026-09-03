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

from typing import Any

from .repro import reproducibility_score
from .sanitize import scan_object_detailed
from .schemas import validate_result
from .stats import summarize
from .trust import TRUST_STATES, effective_trust

__all__ = [
    "data_quality_report",
    "invalidate_result",
    "flag_anomalies",
    "TRUST_STATES",
]


def _privacy_scan(result: dict[str, Any]) -> list[str]:
    """Canonical privacy scan (delegates to aihwbench.sanitize).

    Returns deduplicated pattern ids, in deterministic registry order.
    All detection semantics — patterns, recursion, redaction — live in
    the canonical scanner; this module adds no rules of its own.
    """
    findings = scan_object_detailed(result)
    return list(dict.fromkeys(item["pattern"] for item in findings))


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

    trust = effective_trust(result)

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


def _comparability_profile(result: dict[str, Any]) -> tuple[str, str, str, str]:
    """Return the dimensions that make results statistically comparable.

    Never compare heterogeneous models/workloads/hardware as one population:
    a z-score across unrelated runs is meaningless. Cohort key = protocol,
    runtime, model and device-class. A result with no runtime is its own
    cohort (incomparable), preventing accidental cross-cohort flags.
    """
    runtime = (result.get("runtime") or {}).get("name") or "unknown-runtime"
    model = (result.get("model") or {}).get("name") or "unknown-model"
    protocol = result.get("protocol_version") or "unknown-protocol"
    dev = (result.get("runtime") or {}).get("device") or "unknown-device"
    return (protocol, runtime, model, dev)


def _cohort_anomalies(
    values: list[float], z_threshold: float
) -> tuple[float, float | None, float | None]:
    """Robust MAD-based cohort statistics.

    The median and MAD are resilient to the outliers we are trying to find
    (unlike mean/stddev which are pulled by them). Returns
    ``(median, mad, cohort_size)``; for n < minimum the cohort yields no
    signal (a single dominant group that is 100% of the data cannot be
    "anomalous").
    """
    n = len(values)
    if n < 5:  # minimum meaningful sample for a robust comparison
        return 0.0, None, None
    ordered = sorted(values)
    median = ordered[n // 2] if n % 2 == 1 else (ordered[n // 2 - 1] + ordered[n // 2]) / 2
    deviations = [abs(v - median) for v in ordered]
    deviations.sort()
    dn = len(deviations)
    mad = (
        deviations[dn // 2] if dn % 2 == 1 else (deviations[dn // 2 - 1] + deviations[dn // 2]) / 2
    )
    # If MAD is 0, fall back to a scaled z-score using the cohort stddev so
    # degenerate cohorts (all-but-one identical) still work safely.
    if mad == 0.0:
        mean = sum(values) / n
        var = sum((v - mean) ** 2 for v in values) / (n - 1)
        stddev = var**0.5
        if stddev == 0.0:
            return median, 0.0, None
        return median, 0.0, stddev
    return median, mad, None


def flag_anomalies(
    results: list[dict[str, Any]],
    metric: str = "generation_tokens_per_second",
    z_threshold: float = 3.5,
) -> list[dict[str, Any]]:
    """Flag results that deviate > ``z_threshold`` sigma from their cohort.

    Cohort = same protocol, runtime, model and device class, so heterogeneous
    results are never compared as one population. Uses median/MAD (robust to
    the outliers being sought) rather than mean/stddev, and requires a
    minimum cohort size. Flags request human review; they never assert fraud
    and never remove results automatically.
    """
    by_cohort: dict[tuple[str, str, str, str], list[tuple[str | None, float]]] = {}
    for r in results:
        key = _comparability_profile(r)
        value = (r.get("metrics") or {}).get(metric)
        if value is None:
            continue
        by_cohort.setdefault(key, []).append((r.get("run_id"), float(value)))

    flags: list[dict[str, Any]] = []
    for key, members in by_cohort.items():
        protocol, runtime, model, device = key
        values = [v for _, v in members]
        median, mad, stddev = _cohort_anomalies(values, z_threshold)
        if mad is None:
            continue  # cohort too small or degenerate; nothing robust to say
        for run_id, value in members:
            # Use MAD-based z unless the cohort collapsed (MAD==0), then stddev.
            if mad > 0.0:
                z = (value - median) / (1.4826 * mad)
            elif stddev and stddev > 0.0:
                z = (value - median) / stddev
            else:
                continue
            if abs(z) > z_threshold:
                flags.append(
                    {
                        "run_id": run_id,
                        "metric": metric,
                        "value": value,
                        "z_score": round(z, 3),
                        "cohort": {
                            "protocol": protocol,
                            "runtime": runtime,
                            "model": model,
                            "device": device,
                        },
                        "cohort_size": len(values),
                        "cohort_median": round(median, 3),
                        "cohort_mad": round(mad, 3),
                        "method": "median_mad",
                        "action": "manual_review",
                    }
                )
    return flags
