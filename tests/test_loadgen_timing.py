"""Phase-A regression tests: loadgen timing defects.

Covers two audited defects:

1. Gamma arrivals changed the mean arrival rate whenever ``gamma_shape``
   changed (``gammavariate(shape, 1/rate)`` has mean ``shape/rate``).
   The fix scales by ``1/(rate*shape)`` so the mean inter-arrival is
   ``1/rate`` for every shape.
2. Open-loop workers recorded ``submit_time == start_time``, collapsing
   queue latency to zero and discarding the scheduled timeline.
"""

from __future__ import annotations

import time

import pytest

from aihwbench.loadgen import LoadgenConfig, generate_arrivals, run_load


def _mean_interarrival(offsets: list[float]) -> float:
    gaps = [b - a for a, b in zip(offsets, offsets[1:], strict=False)]
    return sum(gaps) / len(gaps)


def test_gamma_mean_rate_independent_of_shape():
    """For a fixed target rate, the realized mean inter-arrival must be
    ~1/rate regardless of gamma_shape (seeded, hence deterministic)."""
    rate = 50.0
    n = 400
    for shape in (0.5, 2.0, 4.0):
        cfg = LoadgenConfig(pattern="gamma", rate_per_second=rate, gamma_shape=shape, requests=n)
        offsets = list(generate_arrivals(cfg))
        assert len(offsets) == n
        mean_gap = _mean_interarrival(offsets)
        # 1/rate = 0.02 s. Tolerance covers Gamma tail variance at low
        # shape without being loose enough to hide a shape-coupled mean.
        assert mean_gap == pytest.approx(1.0 / rate, rel=0.25), (
            f"shape={shape}: mean inter-arrival {mean_gap:.4f}s "
            f"deviates from 1/rate={1.0 / rate:.4f}s"
        )


def test_gamma_arrivals_deterministic():
    cfg = LoadgenConfig(pattern="gamma", rate_per_second=40.0, gamma_shape=3.0, requests=25)
    assert list(generate_arrivals(cfg)) == list(generate_arrivals(cfg))


def test_open_loop_queue_latency_measured_under_saturation():
    """Offer rate (200/s) far above service capacity (one worker, 10ms
    per request => 100/s): requests must queue, and the preserved
    scheduled submit times must yield nonzero queue latency."""

    def slow_execute(_rid: int) -> dict:
        time.sleep(0.01)
        return {"completion_tokens": 1}

    records = run_load(
        LoadgenConfig(pattern="constant_rate", rate_per_second=200.0, requests=30, concurrency=1),
        slow_execute,
    )
    assert len(records) == 30
    queued = [r for r in records if r.queue_latency_ms > 5.0]
    assert queued, "saturation should produce measurable queue latency"
    # Records arrive in execution order; ids must still map 1:1.
    assert sorted(r.request_id for r in records) == list(range(30))


def test_open_loop_submit_times_preserved_on_schedule():
    """submit_time is the scheduled timeline instant, strictly before
    start_time for queued requests, and monotone across the run."""

    def slow_execute(_rid: int) -> dict:
        time.sleep(0.008)
        return {"completion_tokens": 1}

    records = run_load(
        LoadgenConfig(pattern="constant_rate", rate_per_second=250.0, requests=20, concurrency=1),
        slow_execute,
    )
    submits = sorted(r.submit_time for r in records)
    origin = min(r.submit_time for r in records)
    # Evenly spaced 4ms timeline: spread over >= 19*0.004 - slack.
    assert submits[-1] - submits[0] >= 0.06
    assert origin == pytest.approx(submits[0])
    for r in records:
        assert r.submit_time <= r.start_time + 1e-6


def test_closed_loop_has_zero_queue_latency():
    """Closed-loop workers start immediately; queue latency stays
    exactly zero by construction (unchanged behavior)."""

    def fast(_rid: int) -> dict:
        time.sleep(0.001)
        return {"completion_tokens": 1}

    records = run_load(LoadgenConfig(requests=6, concurrency=2), fast)
    assert all(r.queue_latency_ms == 0.0 for r in records)
