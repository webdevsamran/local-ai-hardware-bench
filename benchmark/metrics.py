"""Metric computation helpers.

All functions operate on measured values only. When an input required
for a derived metric is missing, the derived metric is None.
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from typing import Any


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

    def hi(values: Sequence[float]) -> float | None:
        return round(max(values), 2) if values else None

    gen_tps_mean = mean(gen_tps)
    power_mean = mean(
        [float(v) for it in iterations if (v := it.get("average_power_watts")) is not None]
    )

    return {
        "load_time_ms": lo(loads),
        "ttft_ms": median(ttfts) if ttfts else mean([float(v) for v in ttfts]),
        "prompt_tokens_per_second": median(prompt_tps),
        "generation_tokens_per_second": gen_tps_mean,
        "total_latency_ms": median(latencies) if latencies else mean([float(v) for v in latencies]),
        "p50_latency_ms": round(percentile(latencies, 50), 2) if latencies else None,
        "p90_latency_ms": round(percentile(latencies, 90), 2) if latencies else None,
        "p95_latency_ms": round(percentile(latencies, 95), 2) if latencies else None,
        "p99_latency_ms": round(percentile(latencies, 99), 2) if latencies else None,
        "latency_stddev_ms": stddev(latencies),
        "latency_min_ms": lo(latencies),
        "latency_max_ms": hi(latencies),
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
        "coverage": {
            "iterations": len(iterations),
            "ttft_measured": len(ttfts),
            "latency_measured": len(latencies),
            "gen_tps_measured": len(gen_tps),
        },
    }
