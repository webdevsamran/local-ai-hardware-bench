"""Metric computation helpers.

All functions operate on measured values only. When an input required
for a derived metric is missing, the derived metric is None.

Metric-name contract
--------------------
The canonical metric vocabulary (schema 2.0 / SDK / exporters / frontend)
is defined here once: ``METRIC_REGISTRY`` maps each canonical id to its
unit and any legacy aliases still found in older result documents.
``resolve_metric`` reads a metrics block using the canonical id first and
falls back to legacy aliases, so old documents never lose data.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Mapping, Sequence
from typing import Any

# Canonical metric id -> {"unit": str, "aliases": tuple[str, ...], "family": str}
# Canonical ids MUST match the schema vocabulary (see aihwbench/schemas.py
# ``_METRIC_FIELDS``). Aliases are read-only compatibility names emitted by
# older versions of the aggregator/exporters; they are never written now.
METRIC_REGISTRY: dict[str, dict[str, Any]] = {
    "load_time_ms": {"unit": "ms", "aliases": (), "family": "latency"},
    "ttft_ms": {"unit": "ms", "aliases": (), "family": "latency"},
    "prompt_tokens_per_second": {"unit": "tokens/s", "aliases": (), "family": "throughput"},
    "generation_tokens_per_second": {
        "unit": "tokens/s",
        "aliases": (),
        "family": "throughput",
    },
    "throughput_inferences_per_second": {
        "unit": "inferences/s",
        "aliases": (),
        "family": "throughput",
    },
    "total_latency_ms": {"unit": "ms", "aliases": (), "family": "latency"},
    "median_latency_ms": {"unit": "ms", "aliases": (), "family": "latency"},
    "p50_latency_ms": {"unit": "ms", "aliases": ("latency_p50_ms",), "family": "latency"},
    "p75_latency_ms": {"unit": "ms", "aliases": ("latency_p75_ms",), "family": "latency"},
    "p90_latency_ms": {"unit": "ms", "aliases": ("latency_p90_ms",), "family": "latency"},
    "p95_latency_ms": {"unit": "ms", "aliases": ("latency_p95_ms",), "family": "latency"},
    "p99_latency_ms": {"unit": "ms", "aliases": ("latency_p99_ms",), "family": "latency"},
    "p99_9_latency_ms": {"unit": "ms", "aliases": ("latency_p99_9_ms",), "family": "latency"},
    "min_latency_ms": {"unit": "ms", "aliases": ("latency_min_ms",), "family": "latency"},
    "max_latency_ms": {"unit": "ms", "aliases": ("latency_max_ms",), "family": "latency"},
    "stddev_latency_ms": {
        "unit": "ms",
        "aliases": ("latency_stddev_ms",),
        "family": "latency",
    },
    "cv_latency": {"unit": "ratio", "aliases": ("latency_cv",), "family": "latency"},
    "ci95_latency_ms": {
        "unit": "ms",
        "aliases": ("latency_ci95_ms",),
        "family": "latency",
    },
    "tpot_ms": {"unit": "ms", "aliases": (), "family": "latency"},
    "itl_ms": {"unit": "ms", "aliases": ("itl_mean_ms",), "family": "latency"},
    "time_to_second_token_ms": {"unit": "ms", "aliases": (), "family": "latency"},
    "inter_chunk_latency_ms": {"unit": "ms", "aliases": (), "family": "latency"},
    "prefill_latency_ms": {"unit": "ms", "aliases": (), "family": "latency"},
    "decode_duration_ms": {"unit": "ms", "aliases": (), "family": "latency"},
    "queue_latency_ms": {"unit": "ms", "aliases": (), "family": "latency"},
    "request_latency_ms": {"unit": "ms", "aliases": (), "family": "latency"},
    "ttft_stddev_ms": {"unit": "ms", "aliases": (), "family": "latency"},
    "generation_tps_stddev": {"unit": "tokens/s", "aliases": (), "family": "throughput"},
    "gen_tps_min": {"unit": "tokens/s", "aliases": (), "family": "throughput"},
    "gen_tps_max": {"unit": "tokens/s", "aliases": (), "family": "throughput"},
    "generation_tps_cv": {"unit": "ratio", "aliases": (), "family": "throughput"},
    "gen_tps_ci95": {
        "unit": "tokens/s",
        "aliases": ("generation_tps_ci95",),
        "family": "throughput",
    },
    "peak_ram_mb": {"unit": "MB", "aliases": (), "family": "telemetry"},
    "peak_vram_mb": {"unit": "MB", "aliases": (), "family": "telemetry"},
    "avg_cpu_util_percent": {"unit": "%", "aliases": (), "family": "telemetry"},
    "avg_gpu_util_percent": {"unit": "%", "aliases": (), "family": "telemetry"},
    "max_temperature_c": {"unit": "degC", "aliases": (), "family": "telemetry"},
    "average_power_watts": {"unit": "W", "aliases": (), "family": "telemetry"},
    "idle_power_watts": {"unit": "W", "aliases": (), "family": "telemetry"},
    "incremental_power_watts": {"unit": "W", "aliases": (), "family": "telemetry"},
    "performance_per_watt": {
        "unit": "tokens/s/W",
        "aliases": (),
        "family": "efficiency",
    },
    "energy_joules_per_token": {
        "unit": "J/token",
        "aliases": ("energy_per_token_joules",),
        "family": "efficiency",
    },
    "energy_joules_per_request": {
        "unit": "J/request",
        "aliases": (),
        "family": "efficiency",
    },
    "energy_joules_per_1k_tokens": {
        "unit": "J/1k tokens",
        "aliases": (),
        "family": "efficiency",
    },
    "requests_per_second": {"unit": "requests/s", "aliases": (), "family": "capacity"},
    "error_rate": {"unit": "ratio", "aliases": (), "family": "capacity"},
}


class _Missing:
    """Sentinel distinguishing "metric absent" from a null value."""

    def __repr__(self) -> str:  # pragma: no cover - debug aid only
        return "<METRIC_MISSING>"


_MISSING = _Missing()


def resolve_metric(metrics: Mapping[str, Any], canonical_id: str) -> Any:
    """Read a metric by canonical id with legacy-alias fallback.

    Returns the metrics-block value (which may be None for "not
    measured") when either the canonical name or one of its registered
    legacy aliases is present; returns the ``_MISSING`` sentinel only when
    the metric is absent entirely, so callers can tell "absent" from
    "null".
    """
    if canonical_id in metrics:
        return metrics[canonical_id]
    for alias in METRIC_REGISTRY.get(canonical_id, {}).get("aliases", ()):
        if alias in metrics:
            return metrics[alias]
    return _MISSING


def has_metric(metrics: dict[str, Any], canonical_id: str) -> bool:
    """True when the metric is present (by canonical id or alias)."""
    return resolve_metric(metrics, canonical_id) is not _MISSING


def percentile(values: Sequence[float], pct: float) -> float | None:
    """Linear-interpolated percentile of a non-empty sequence."""
    if not values:
        return None
    if not 0.0 <= pct <= 100.0:
        raise ValueError("pct must be in [0, 100]")
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    rank = (pct / 100.0) * (len(ordered) - 1)
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = rank - lower
    return float(ordered[lower] * (1 - fraction) + ordered[upper] * fraction)


def safe_div(numerator: float | None, denominator: float | None) -> float | None:
    """Divide two optional numbers; None if either is missing or zero."""
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def tokens_per_second(token_count: int | None, duration_seconds: float | None) -> float | None:
    """Tokens per second from a count and duration in seconds."""
    if token_count is None or duration_seconds is None or duration_seconds <= 0:
        return None
    return token_count / duration_seconds


def performance_per_watt(
    generation_tokens_per_second: float | None,
    average_power_watts: float | None,
) -> float | None:
    """Generation throughput per watt (tokens/s/W)."""
    return safe_div(generation_tokens_per_second, average_power_watts)


def aggregate_iteration_metrics(iterations: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate per-iteration measurements into final schema metrics.

    Each iteration dict may contain:
      load_time_ms, ttft_ms, total_latency_ms,
      prompt_tokens, prompt_eval_seconds,
      completion_tokens, eval_seconds

    Missing inputs produce None for the corresponding output metric.
    """
    ttfts = [it["ttft_ms"] for it in iterations if it.get("ttft_ms") is not None]
    latencies = [
        it["total_latency_ms"] for it in iterations if it.get("total_latency_ms") is not None
    ]
    loads = [it["load_time_ms"] for it in iterations if it.get("load_time_ms") is not None]

    prompt_tps_values = [
        tokens_per_second(it.get("prompt_tokens"), it.get("prompt_eval_seconds"))
        for it in iterations
    ]
    gen_tps_values = [
        tokens_per_second(it.get("completion_tokens"), it.get("eval_seconds")) for it in iterations
    ]
    prompt_tps = [v for v in prompt_tps_values if v is not None]
    gen_tps = [v for v in gen_tps_values if v is not None]

    def mean(values: Sequence[float]) -> float | None:
        return round(sum(values) / len(values), 2) if values else None

    def median(values: Sequence[float]) -> float | None:
        if not values:
            return None
        return round(statistics.median(values), 2)

    def stddev(values: Sequence[float]) -> float | None:
        if len(values) < 2:
            return None
        return round(statistics.pstdev(values), 2)

    def lo(values: Sequence[float]) -> float | None:
        return round(min(values), 2) if values else None

    def cv(values: Sequence[float]) -> float | None:
        """Coefficient of variation (stddev/mean); None if undefined."""
        if len(values) < 2:
            return None
        mu = sum(values) / len(values)
        if mu == 0:
            return None
        return round(statistics.pstdev(values) / abs(mu), 4)

    def ci95(values: Sequence[float]) -> list[float] | None:
        """95% CI of the mean (normal approximation; n>=2)."""
        if len(values) < 2:
            return None
        mu = sum(values) / len(values)
        se = statistics.pstdev(values) / math.sqrt(len(values))
        return [round(mu - 1.96 * se, 2), round(mu + 1.96 * se, 2)]

    def hi(values: Sequence[float]) -> float | None:
        return round(max(values), 2) if values else None

    def pct(values: Sequence[float], q: float) -> float | None:
        v = percentile(values, q)
        return round(v, 2) if v is not None else None

    gen_tps_mean = mean(gen_tps)
    eval_seconds_list = [float(v) for it in iterations if (v := it.get("eval_seconds")) is not None]
    completion_tokens_list = [
        float(v) for it in iterations if (v := it.get("completion_tokens")) is not None
    ]
    mean_eval_s = (
        round(sum(eval_seconds_list) / len(eval_seconds_list), 6) if eval_seconds_list else None
    )
    mean_tokens = (
        round(sum(completion_tokens_list) / len(completion_tokens_list), 3)
        if completion_tokens_list
        else None
    )
    power_mean = mean(
        [float(v) for it in iterations if (v := it.get("average_power_watts")) is not None]
    )

    return {
        "load_time_ms": lo(loads),
        "ttft_ms": median(ttfts) if ttfts else mean([float(v) for v in ttfts]),
        "prompt_tokens_per_second": median(prompt_tps),
        "generation_tokens_per_second": gen_tps_mean,
        "total_latency_ms": (
            median(latencies) if latencies else mean([float(v) for v in latencies])
        ),
        "p50_latency_ms": pct(latencies, 50) if latencies else None,
        "p90_latency_ms": pct(latencies, 90) if latencies else None,
        "p95_latency_ms": pct(latencies, 95) if latencies else None,
        "p99_latency_ms": pct(latencies, 99) if latencies else None,
        "stddev_latency_ms": stddev(latencies),
        "min_latency_ms": lo(latencies),
        "max_latency_ms": hi(latencies),
        "ttft_stddev_ms": stddev([float(v) for v in ttfts]),
        "generation_tps_stddev": stddev(gen_tps),
        "gen_tps_min": lo(gen_tps),
        "gen_tps_max": hi(gen_tps),
        "peak_ram_mb": None,
        "peak_vram_mb": None,
        "avg_cpu_util_percent": None,
        "avg_gpu_util_percent": None,
        "max_temperature_c": None,
        "average_power_watts": power_mean,
        "performance_per_watt": performance_per_watt(gen_tps_mean, power_mean),
        "generation_tps_cv": cv(gen_tps),
        "ci95_latency_ms": ci95(latencies),
        "gen_tps_ci95": ci95(gen_tps),
        "itl_ms": (
            round(1000.0 * mean_eval_s / mean_tokens, 3) if mean_eval_s and mean_tokens else None
        ),
        "energy_joules_per_token": (
            round(power_mean / gen_tps_mean, 4) if power_mean and gen_tps_mean else None
        ),
        "coverage": {
            "iterations": len(iterations),
            "ttft_measured": len(ttfts),
            "latency_measured": len(latencies),
            "gen_tps_measured": len(gen_tps),
        },
    }
