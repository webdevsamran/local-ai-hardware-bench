"""Capacity testing (#8).

Runs a concurrency ladder (closed-loop load at increasing concurrency
levels) and computes per-level req/s, throughput, p95/p99 latency, TTFT,
and error rate — then identifies the *sustainable* concurrency under an
explicit, documented rule:

    sustainable = highest concurrency level where error_rate == 0 AND
                  p95 latency <= sustainability_factor x the best
                  (lowest) level's p95.

The rule is reported alongside the verdict so it can be audited or
changed; it is never hidden inside an opaque score.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .loadgen import LoadgenConfig, RequestRecord, run_load
from .stats import summarize

__all__ = ["CapacityConfig", "run_capacity_ladder", "LevelResult", "CapacityReport"]

ExecuteFn = Callable[[int], dict[str, Any]]


@dataclass(frozen=True)
class CapacityConfig:
    concurrency_levels: tuple[int, ...] = (1, 2, 4, 8)
    requests_per_level: int = 20
    seed: int = 42
    # p95 may degrade up to this multiple vs the best level before the
    # level is considered beyond sustainable capacity.
    sustainability_factor: float = 2.0

    def __post_init__(self) -> None:
        if not self.concurrency_levels:
            raise ValueError("concurrency_levels must not be empty")
        if any(c < 1 for c in self.concurrency_levels):
            raise ValueError("concurrency levels must be >= 1")
        if self.requests_per_level < 1:
            raise ValueError("requests_per_level must be >= 1")


@dataclass
class LevelResult:
    concurrency: int
    requests: int
    errors: int
    requests_per_second: float | None
    throughput_tokens_per_second: float | None
    ttft_ms_mean: float | None
    p95_latency_ms: float | None
    p99_latency_ms: float | None
    mean_queue_latency_ms: float | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "concurrency": self.concurrency,
            "requests": self.requests,
            "errors": self.errors,
            "requests_per_second": self.requests_per_second,
            "throughput_tokens_per_second": self.throughput_tokens_per_second,
            "ttft_ms_mean": self.ttft_ms_mean,
            "p95_latency_ms": self.p95_latency_ms,
            "p99_latency_ms": self.p99_latency_ms,
            "mean_queue_latency_ms": self.mean_queue_latency_ms,
        }


@dataclass
class CapacityReport:
    levels: list[LevelResult]
    sustainable_concurrency: int | None
    rule: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "levels": [lv.as_dict() for lv in self.levels],
            "sustainable_concurrency": self.sustainable_concurrency,
            "rule": self.rule,
        }


def _level_result(concurrency: int, records: list[RequestRecord]) -> LevelResult:
    latencies = [r.request_latency_ms for r in records if r.success]
    wall = max((r.end_time for r in records), default=0.0) - min(
        (r.submit_time for r in records), default=0.0
    )
    tokens = sum(r.result.get("completion_tokens", 0) or 0 for r in records if r.success)
    ttfts = [
        r.result["ttft_ms"] for r in records if r.success and r.result.get("ttft_ms") is not None
    ]
    queue = [r.queue_latency_ms for r in records]
    summary = summarize(latencies)
    return LevelResult(
        concurrency=concurrency,
        requests=len(records),
        errors=sum(1 for r in records if not r.success),
        requests_per_second=(len(records) / wall) if wall > 0 else None,
        throughput_tokens_per_second=(tokens / wall) if wall > 0 and tokens else None,
        ttft_ms_mean=(sum(ttfts) / len(ttfts)) if ttfts else None,
        p95_latency_ms=summary["p95"],
        p99_latency_ms=summary["p99"],
        mean_queue_latency_ms=(sum(queue) / len(queue)) if queue else None,
    )


def run_capacity_ladder(config: CapacityConfig, execute: ExecuteFn) -> CapacityReport:
    """Run every concurrency level and compute the sustainable verdict."""
    levels: list[LevelResult] = []
    for concurrency in config.concurrency_levels:
        lc = LoadgenConfig(
            pattern="closed_loop",
            concurrency=concurrency,
            requests=config.requests_per_level,
            seed=config.seed + concurrency,
        )
        records = run_load(lc, execute)
        levels.append(_level_result(concurrency, records))

    measured = [lv for lv in levels if lv.p95_latency_ms is not None and lv.errors == 0]
    sustainable: int | None = None
    if measured:
        best_p95 = min(lv.p95_latency_ms for lv in measured)
        threshold = config.sustainability_factor * best_p95
        ok = [lv for lv in measured if lv.p95_latency_ms <= threshold]
        sustainable = max(ok, key=lambda lv: lv.concurrency).concurrency if ok else None
    rule = (
        f"sustainable = max concurrency with error_rate == 0 and "
        f"p95 <= {config.sustainability_factor:g}x best-level p95"
    )
    return CapacityReport(levels=levels, sustainable_concurrency=sustainable, rule=rule)
