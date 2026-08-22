"""Expanded descriptive statistics (#10).

Adds median, p50/p75/p90/p95/p99/p99.9, min/max, stddev, coefficient of
variation, and *optional* bootstrap confidence intervals.

Honesty rule: confidence intervals are returned as ``None`` when the
sample count is below ``min_samples_for_ci`` (default 20). Confidence is
never manufactured from too few samples.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from typing import Any

from .metrics import percentile

__all__ = [
    "MIN_SAMPLES_FOR_CI",
    "summarize",
    "bootstrap_ci",
]

MIN_SAMPLES_FOR_CI = 20


def bootstrap_ci(
    values: Sequence[float],
    statistic: str = "mean",
    confidence: float = 0.95,
    iterations: int = 2000,
    seed: int = 42,
    min_samples: int = MIN_SAMPLES_FOR_CI,
) -> tuple[float, float] | None:
    """Percentile bootstrap CI for a statistic.

    Returns None when ``len(values) < min_samples`` — insufficient data is
    reported as "no interval", never as a fabricated one.
    """
    if len(values) < min_samples:
        return None

    def _stat(sample: list[float]) -> float:
        if statistic == "mean":
            return sum(sample) / len(sample)
        if statistic == "median":
            return percentile(sample, 50) or 0.0
        raise ValueError(f"unsupported statistic {statistic!r}")

    rng = random.Random(f"aihwbench-bootstrap-{statistic}-{seed}")
    n = len(values)
    stats: list[float] = []
    for _ in range(iterations):
        sample = [values[rng.randrange(n)] for _ in range(n)]
        stats.append(_stat(sample))
    stats.sort()
    alpha = (1.0 - confidence) / 2.0
    lo = percentile(stats, alpha * 100)
    hi = percentile(stats, (1.0 - alpha) * 100)
    if lo is None or hi is None:
        return None
    return (lo, hi)


def summarize(
    values: Sequence[float],
    include_ci: bool = False,
    seed: int = 42,
) -> dict[str, Any]:
    """Full descriptive summary of a latency/throughput sample.

    All fields are measured from the provided values; empty input yields a
    summary of all-None statistics rather than zeros.
    """
    if not values:
        return {
            "count": 0,
            "mean": None,
            "median": None,
            "p50": None,
            "p75": None,
            "p90": None,
            "p95": None,
            "p99": None,
            "p99_9": None,
            "min": None,
            "max": None,
            "stddev": None,
            "cv": None,
            "ci95": None,
        }
    ordered = sorted(values)
    count = len(ordered)
    mean = sum(ordered) / count
    variance = sum((v - mean) ** 2 for v in ordered) / (count - 1) if count > 1 else 0.0
    stddev = variance**0.5
    cv = (stddev / mean) if mean > 0 else None
    ci = bootstrap_ci(list(values), seed=seed) if include_ci else None
    return {
        "count": count,
        "mean": mean,
        "median": percentile(ordered, 50),
        "p50": percentile(ordered, 50),
        "p75": percentile(ordered, 75),
        "p90": percentile(ordered, 90),
        "p95": percentile(ordered, 95),
        "p99": percentile(ordered, 99),
        "p99_9": percentile(ordered, 99.9),
        "min": ordered[0],
        "max": ordered[-1],
        "stddev": stddev,
        "cv": cv,
        "ci95": list(ci) if ci is not None else None,
    }
