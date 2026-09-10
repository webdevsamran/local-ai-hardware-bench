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

from .plausibility import check_plausibility
from .repro import reproducibility_score
from .sanitize import scan_object_detailed
from .schemas import validate_result
from .stats import summarize
from .trust import TRUST_STATES, effective_trust

__all__ = [
    "data_quality_report",
    "per_iteration_throughput",
    "throughput_decline",
    "MAX_ACCEPTABLE_CV",
    "SUSTAINED_DECLINE_FRACTION",
    "invalidate_result",
    "flag_anomalies",
    "statistical_confidence",
    "MIN_PUBLISHED_ITERATIONS",
    "MIN_WARMUP_RUNS",
    "TRUST_STATES",
]

#: The published statistical policy, from docs/methodology.md: "Minimum 5
#: measured iterations after 2 warm-ups for published results." It was stated
#: and never enforced, so a single-run number could be published looking
#: exactly like a five-iteration one.
MIN_PUBLISHED_ITERATIONS = 5
MIN_WARMUP_RUNS = 2

#: Coefficient of variation above which a measured series is too unstable for
#: its mean to be published as a headline figure.
#:
#: Applied to generation throughput as well as latency. Latency alone was not
#: enough: in a short-generation workload, total latency is dominated by
#: time-to-first-token, so a run whose throughput fell 327 -> 84 tok/s across
#: five iterations (CV 0.56) still showed a latency CV of 0.06 and passed. The
#: headline number on the leaderboard is tokens per second, and it was the one
#: number whose stability nothing checked.
MAX_ACCEPTABLE_CV = 0.5

#: Fraction by which throughput must fall from the first measured iteration to
#: the last before the decline is called sustained rather than noise.
#:
#: A monotonic slide is a different finding from a noisy one and has a
#: different cause -- thermal or power limits engaging partway through, which
#: is a property of the machine worth reporting rather than a defect in the
#: measurement. Reporting it separately is what turns "this number is
#: unreliable" into "this machine cannot hold this rate".
SUSTAINED_DECLINE_FRACTION = 0.25


def statistical_confidence(result: dict[str, Any]) -> dict[str, Any]:
    """How much statistical weight a result's numbers carry.

    A single measurement and a five-iteration median look identical once
    rendered as "110.93 tok/s". Labelling the difference is the minimum honest
    treatment; refusing to publish the first outright would lose real data
    from contributors whose hardware cannot sit through a long run.

    ``label`` is one of:

    - ``compliant``   — meets the published policy
    - ``single_run``  — one measured iteration; the number has no spread at all
    - ``below_policy``— measured more than once, but under the minimum
    - ``unstated``    — the iteration count was not recorded, which is its own
      problem: an unstated protocol cannot be reproduced
    """
    repro = result.get("reproducibility") or {}
    iterations = repro.get("iterations")
    warmups = repro.get("warmup_runs")

    if not isinstance(iterations, (int, float)) or isinstance(iterations, bool):
        return {
            "label": "unstated",
            "iterations": None,
            "warmup_runs": warmups,
            "meets_policy": False,
            "detail": (
                "the iteration count was not recorded; a measurement protocol "
                "that is not stated cannot be reproduced or weighed"
            ),
        }

    iterations = int(iterations)
    unwarmed = not isinstance(warmups, (int, float)) or int(warmups) < MIN_WARMUP_RUNS
    if iterations <= 1:
        label = "single_run"
        detail = (
            "a single measured iteration: this number has no spread, so no "
            "confidence interval or variance can be derived from it"
        )
    elif iterations < MIN_PUBLISHED_ITERATIONS:
        label = "below_policy"
        detail = (
            f"{iterations} iterations, below the published minimum of {MIN_PUBLISHED_ITERATIONS}"
        )
    else:
        label = "compliant"
        detail = f"{iterations} measured iterations"

    if label == "compliant" and unwarmed:
        label = "below_policy"
        detail = (
            f"{iterations} iterations but {warmups} warm-up run(s), below the "
            f"minimum of {MIN_WARMUP_RUNS}: cold-start cost is inside the "
            "measurement"
        )

    return {
        "label": label,
        "iterations": iterations,
        "warmup_runs": warmups if isinstance(warmups, (int, float)) else None,
        "meets_policy": label == "compliant",
        "detail": detail,
    }


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
    latencies = _iteration_latencies(iterations)
    variance = summarize(latencies) if latencies else None
    latency_cv = variance["cv"] if variance else None

    # The headline metric's own stability. Computed by the metrics layer on
    # every run and, until now, consulted by nothing.
    throughput = per_iteration_throughput(iterations)
    throughput_variance = summarize(throughput) if throughput else None
    throughput_cv = (result.get("metrics") or {}).get("generation_tps_cv")
    if throughput_cv is None and throughput_variance:
        throughput_cv = throughput_variance["cv"]

    high_variance = any(
        value is not None and value > MAX_ACCEPTABLE_CV for value in (latency_cv, throughput_cv)
    )
    # Whether stability was checked at all.
    #
    # `variance_acceptable` means "not known to be unstable", and for four
    # published results it was passing on nothing: the graph backends record
    # per-iteration timing as `latency_ms` while this looked only for
    # `total_latency_ms`, and they carry no token counts, so neither series
    # existed. A check that cannot fail is the same defect as one that always
    # does, and this says which happened.
    variance_measured = latency_cv is not None or throughput_cv is not None
    decline = throughput_decline(throughput)

    # Whether the machine was available to be measured.
    #
    # A benchmark taken under contention describes the contention. Measured
    # here: an ONNX Runtime CPU run reported 2.53 inferences per second where
    # the same model on the same machine had done 299.92, because an antivirus
    # scan held the CPU at 68%. It passed every other check — consistent, so
    # variance was low; internally coherent, so plausibility was clean — and a
    # 118x error went to publication looking like a measurement.
    #
    # Unknown load is not a failure. `busy: None` means psutil was absent, and
    # refusing to publish for want of an optional dependency would be a worse
    # rule than the one it replaced.
    contention = (result.get("reproducibility") or {}).get("machine_contention") or {}
    measured_idle = contention.get("busy") is not True

    trust = effective_trust(result)
    confidence = statistical_confidence(result)
    # Impossible and self-contradictory values. Findings are review requests,
    # never fraud verdicts: the likeliest cause of an impossible number is a
    # measurement bug, which is worth finding for its own sake.
    implausible = check_plausibility(result)

    checks = {
        "schema_valid": not schema_errors,
        "schema_errors": schema_errors,
        "privacy_clean": not privacy_hits,
        "privacy_hits": privacy_hits,
        "provenance_present": bool((result.get("provenance") or {}).get("result_hash")),
        "reproducibility_score": repro["score"],
        "variance_acceptable": not high_variance,
        "cv_latency": latency_cv,
        "cv_generation_throughput": throughput_cv,
        # False means the run carried no series to measure, not that it was
        # steady.
        "variance_measured": variance_measured,
        # Present only when throughput slid monotonically: a sustained decline
        # is a statement about the machine, not about the measurement.
        "sustained_decline": decline,
        "trust_state": trust,
        "statistical_confidence": confidence["label"],
        "meets_iteration_policy": confidence["meets_policy"],
        "statistical_confidence_detail": confidence["detail"],
        "values_plausible": not implausible,
        "implausible_values": implausible,
        # False only when load was measured and was above the threshold.
        "measured_on_an_idle_machine": measured_idle,
        "machine_contention": contention or None,
    }
    scored = (
        "schema_valid",
        "privacy_clean",
        "provenance_present",
        "variance_acceptable",
        "values_plausible",
        "measured_on_an_idle_machine",
    )
    passed = sum(1 for key in scored if checks[key])
    return {"checks": checks, "checks_passed": passed, "checks_total": len(scored)}


#: Per-iteration keys carrying a request's wall-clock duration.
#:
#: Generative backends write `total_latency_ms`; the graph backends (ONNX
#: Runtime, OpenVINO) write `latency_ms`, because an inference is not a request
#: with a prompt and a completion. Reading only the first meant four published
#: results had their variance check pass with no series to check.
_LATENCY_KEYS = ("total_latency_ms", "latency_ms")


def _iteration_latencies(iterations: list[Any]) -> list[float]:
    """Per-iteration durations, whichever key the backend used."""
    values: list[float] = []
    for iteration in iterations:
        if not isinstance(iteration, dict):
            continue
        for key in _LATENCY_KEYS:
            value = iteration.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                values.append(float(value))
                break
    return values


def per_iteration_throughput(iterations: list[Any]) -> list[float]:
    """Generation throughput for each iteration, in tokens per second.

    Derived from the tokens produced and the time spent producing them, which
    is the only pair every backend records per iteration. Iterations missing
    either are skipped rather than assumed.
    """
    values: list[float] = []
    for iteration in iterations:
        if not isinstance(iteration, dict):
            continue
        tokens = iteration.get("completion_tokens")
        seconds = iteration.get("eval_seconds")
        if isinstance(tokens, (int, float)) and isinstance(seconds, (int, float)):
            if tokens > 0 and seconds > 0:
                values.append(float(tokens) / float(seconds))
    return values


def throughput_decline(throughput: list[float]) -> dict[str, Any] | None:
    """Describe a sustained fall in throughput across a run, if there is one.

    Compares the mean of the first half of the run against the mean of the
    last half, and reports only when the later half is lower by more than
    ``SUSTAINED_DECLINE_FRACTION``.

    Comparing *halves* rather than the first and last iterations is what makes
    this trustworthy. An endpoint comparison reads a single high opening
    iteration as a collapse: the series 333, 180, 266, 258, 242 tok/s is noise
    that recovers, yet its first and last values differ by 27%. Its halves
    differ by 2%, which is the truth.

    A real decline looks like the reference machine's 327, 342, 118, 124,
    84 tok/s -- halves 69% apart. Published as a mean of 199 tok/s, that
    number describes no moment of the run; the machine never held it.
    """
    if len(throughput) < 4:
        # Halves of a 3-point series share a point or omit one; either way the
        # comparison says more about the split than about the run.
        return None

    midpoint = len(throughput) // 2
    early = throughput[:midpoint]
    late = throughput[len(throughput) - midpoint :]
    early_mean = sum(early) / len(early)
    late_mean = sum(late) / len(late)
    if early_mean <= 0:
        return None

    drop = (early_mean - late_mean) / early_mean
    if drop <= SUSTAINED_DECLINE_FRACTION:
        return None

    return {
        "first_iteration_tps": round(throughput[0], 2),
        "last_iteration_tps": round(throughput[-1], 2),
        "early_mean_tps": round(early_mean, 2),
        "late_mean_tps": round(late_mean, 2),
        "decline_fraction": round(drop, 4),
        "detail": (
            f"generation throughput fell {drop:.0%} between the first and second "
            f"half of the run ({early_mean:.0f} -> {late_mean:.0f} tok/s). The "
            "mean is not a rate this machine sustained; it is likely settling "
            "into a thermal or power limit"
        ),
    }


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
