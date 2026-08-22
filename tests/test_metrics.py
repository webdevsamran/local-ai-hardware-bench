"""Tests for metric computation."""

import pytest

from benchmark.metrics import (
    aggregate_iteration_metrics,
    percentile,
    performance_per_watt,
    safe_div,
    tokens_per_second,
)


def test_percentile_basic():
    assert percentile([1, 2, 3, 4], 50) == 2.5
    assert percentile([10], 95) == 10.0
    assert percentile([1, 2, 3, 4, 5], 0) == 1.0
    assert percentile([1, 2, 3, 4, 5], 100) == 5.0


def test_percentile_empty_returns_none():
    assert percentile([], 50) is None


def test_percentile_invalid_pct_raises():
    with pytest.raises(ValueError):
        percentile([1], 150)


def test_safe_div():
    assert safe_div(10, 2) == 5.0
    assert safe_div(10, 0) is None
    assert safe_div(None, 2) is None
    assert safe_div(10, None) is None


def test_tokens_per_second():
    assert tokens_per_second(128, 2.0) == 64.0
    assert tokens_per_second(128, 0) is None
    assert tokens_per_second(None, 2.0) is None


def test_performance_per_watt():
    assert performance_per_watt(60.0, 30.0) == 2.0
    assert performance_per_watt(60.0, None) is None


def test_aggregate_iterations():
    iterations = [
        {"ttft_ms": 10.0, "total_latency_ms": 100.0,
         "completion_tokens": 100, "eval_seconds": 2.0,
         "prompt_tokens": 20, "prompt_eval_seconds": 0.1},
        {"ttft_ms": 20.0, "total_latency_ms": 200.0,
         "completion_tokens": 100, "eval_seconds": 4.0,
         "prompt_tokens": 20, "prompt_eval_seconds": 0.1},
    ]
    metrics = aggregate_iteration_metrics(iterations)
    assert metrics["ttft_ms"] == 15.0
    assert metrics["p50_latency_ms"] == 150.0
    assert metrics["generation_tokens_per_second"] == pytest.approx(37.5)
    assert metrics["prompt_tokens_per_second"] == pytest.approx(200.0)


def test_aggregate_missing_inputs_yield_none():
    metrics = aggregate_iteration_metrics([{"ttft_ms": 5.0}])
    assert metrics["generation_tokens_per_second"] is None
    assert metrics["performance_per_watt"] is None
    assert metrics["ttft_ms"] == 5.0
