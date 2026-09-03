"""Capacity ladder methodology tests.

Pins the documented sustainability rule: the highest zero-error
concurrency whose p95 stays within ``sustainability_factor`` times the
best (minimum) p95 across measured levels.
"""

from __future__ import annotations

import time

from aihwbench.capacity import (
    CapacityConfig,
    LevelResult,
    _level_result,
    run_capacity_ladder,
    sustainable_concurrency,
)
from aihwbench.loadgen import RequestRecord


def _level(concurrency: int, p95: float | None, errors: int = 0) -> LevelResult:
    return LevelResult(
        concurrency=concurrency,
        requests=20,
        errors=errors,
        requests_per_second=10.0,
        throughput_tokens_per_second=500.0,
        ttft_ms_mean=5.0,
        p95_latency_ms=p95,
        p99_latency_ms=(p95 * 1.1 if p95 is not None else None),
        mean_queue_latency_ms=1.0,
    )


# ---------------------------------------------------------------------------
# Pure selection rule
# ---------------------------------------------------------------------------


def test_sustainable_picks_highest_level_within_threshold():
    levels = [_level(1, 10.0), _level(2, 20.0), _level(4, 21.0), _level(8, 40.0)]
    assert sustainable_concurrency(levels, 2.0) == 2


def test_sustainable_threshold_is_inclusive_at_boundary():
    levels = [_level(1, 10.0), _level(2, 20.0)]
    assert sustainable_concurrency(levels, 2.0) == 2


def test_sustainable_none_when_all_levels_error():
    levels = [_level(1, 10.0, errors=1), _level(2, 20.0, errors=1)]
    assert sustainable_concurrency(levels, 2.0) is None


def test_sustainable_none_when_no_measurable_p95():
    levels = [_level(1, None), _level(2, None)]
    assert sustainable_concurrency(levels, 2.0) is None


def test_sustainable_none_when_no_level_within_threshold():
    # With factor >= 1 the best level always qualifies, so use factor < 1.
    levels = [_level(1, 10.0), _level(2, 100.0)]
    assert sustainable_concurrency(levels, 0.5) is None


def test_erroring_level_excluded_from_verdict():
    # Level 2 would be within threshold from its successful subset, but it
    # had errors and must be excluded entirely.
    levels = [_level(1, 10.0), _level(2, 12.0, errors=1), _level(4, 100.0)]
    assert sustainable_concurrency(levels, 2.0) == 1


# ---------------------------------------------------------------------------
# Level summary math over synthetic records
# ---------------------------------------------------------------------------


def _record(request_id: int, latency_ms: float, success: bool = True) -> RequestRecord:
    # submit -> start gap of 5 ms models real queueing; start -> end spans
    # exactly latency_ms.
    t0 = 1000.0 + request_id
    start = t0 + 0.005
    return RequestRecord(
        request_id=request_id,
        submit_time=t0,
        start_time=start,
        end_time=start + latency_ms / 1000.0,
        success=success,
        result={"completion_tokens": 10, "ttft_ms": 1.0},
    )


def test_level_result_summary_math():
    records = [_record(i, 10.0 + i) for i in range(10)] + [_record(100, 0.0, success=False)]
    lv = _level_result(4, records)
    assert lv.concurrency == 4
    assert lv.requests == 11
    assert lv.errors == 1
    # Latencies span 10..19 ms; p95 must land near the top of that range.
    assert lv.p95_latency_ms is not None and 18.0 < lv.p95_latency_ms <= 19.0
    assert lv.throughput_tokens_per_second is not None and lv.throughput_tokens_per_second > 0
    assert lv.ttft_ms_mean == 1.0
    # Queue latency is real: start is scheduled after submit.
    mean_queue = lv.mean_queue_latency_ms
    assert mean_queue is not None and abs(mean_queue - 5.0) < 1e-6


# ---------------------------------------------------------------------------
# Ladder integration
# ---------------------------------------------------------------------------


def test_ladder_equal_latency_sustainable_at_max_level():
    def execute(request_id: int) -> dict:
        time.sleep(0.002)
        return {"completion_tokens": 5, "ttft_ms": 1.0}

    cfg = CapacityConfig(concurrency_levels=(1, 2, 4), requests_per_level=6)
    report = run_capacity_ladder(cfg, execute)
    assert [lv.concurrency for lv in report.levels] == [1, 2, 4]
    assert report.sustainable_concurrency == 4
    assert "2x" in report.rule or "2" in report.rule


def test_ladder_none_when_every_level_errors():
    def execute(request_id: int) -> dict:
        raise RuntimeError("backend down")

    cfg = CapacityConfig(concurrency_levels=(1, 2), requests_per_level=3)
    report = run_capacity_ladder(cfg, execute)
    assert all(lv.errors == lv.requests for lv in report.levels)
    assert report.sustainable_concurrency is None


def test_capacity_config_validation():
    for bad in (
        {"concurrency_levels": ()},
        {"concurrency_levels": (0, 1)},
        {"requests_per_level": 0},
    ):
        try:
            CapacityConfig(**bad)
        except ValueError:
            continue
        raise AssertionError(f"CapacityConfig accepted {bad}")
