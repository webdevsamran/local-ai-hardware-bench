"""Tests for metric computation."""

import pytest

from aihwbench.metrics import (
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
        {
            "ttft_ms": 10.0,
            "total_latency_ms": 100.0,
            "completion_tokens": 100,
            "eval_seconds": 2.0,
            "prompt_tokens": 20,
            "prompt_eval_seconds": 0.1,
        },
        {
            "ttft_ms": 20.0,
            "total_latency_ms": 200.0,
            "completion_tokens": 100,
            "eval_seconds": 4.0,
            "prompt_tokens": 20,
            "prompt_eval_seconds": 0.1,
        },
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


# --------------------------------------------------------------- cold start
#
# The first request after a model is not resident pays for loading it; every
# request after does not. Warm-up runs were discarded entirely, so the only
# cold-start measurement a run could produce was thrown away -- even though
# "how long until this is usable" is a real part of using a local model, and
# on a machine where the model does not stay resident it is paid repeatedly.


def test_cold_start_comes_from_the_first_warmup():
    from aihwbench.metrics import cold_start_metrics

    report = cold_start_metrics(
        [{"load_time_ms": 2400.0}, {"load_time_ms": None}],
        [{"load_time_ms": 12.0}, {"load_time_ms": 14.0}],
    )
    assert report["cold_start_ms"] == 2400.0
    assert report["warm_load_ms"] == 13.0
    assert report["cold_start_penalty_ms"] == 2387.0
    assert report["cold_start_measured"] is True


def test_a_resident_model_reports_the_whole_cold_figure_as_the_penalty():
    """No load reported on measured runs means the model stayed loaded."""
    from aihwbench.metrics import cold_start_metrics

    report = cold_start_metrics([{"load_time_ms": 2400.0}], [{"load_time_ms": None}] * 5)
    assert report["cold_start_penalty_ms"] == 2400.0


def test_an_already_warm_run_measures_no_cold_start():
    """Absent, not zero: the run simply never loaded the model."""
    from aihwbench.metrics import cold_start_metrics

    report = cold_start_metrics([{"load_time_ms": None}], [{"load_time_ms": None}])
    assert report["cold_start_ms"] is None
    assert report["cold_start_measured"] is False
    assert report["cold_start_penalty_ms"] is None


def test_no_warmups_means_no_cold_start_measurement():
    from aihwbench.metrics import cold_start_metrics

    report = cold_start_metrics([], [{"load_time_ms": 10.0}])
    assert report["cold_start_measured"] is False


def test_cold_start_ignores_non_numeric_load_times():
    from aihwbench.metrics import cold_start_metrics

    report = cold_start_metrics([{"load_time_ms": "fast"}], [{"load_time_ms": True}])
    assert report["cold_start_ms"] is None
    assert report["warm_load_ms"] is None


def test_a_cold_load_no_slower_than_warm_is_not_a_cold_start():
    """Found on real hardware: the penalty went negative.

    Running the agentic workload left the model resident, so the first
    warm-up loaded nothing and its "cold" figure came in fractionally below
    the warm mean. A negative penalty is meaningless and zero would claim
    loading is free, so neither is reported -- but both raw figures stay
    visible so a reader can see why.
    """
    from aihwbench.metrics import cold_start_metrics

    report = cold_start_metrics([{"load_time_ms": 11.0}], [{"load_time_ms": 12.2}])
    assert report["cold_start_penalty_ms"] is None
    assert report["cold_start_measured"] is False
    assert report["cold_start_ms"] == 11.0
    assert report["warm_load_ms"] == 12.2


def test_the_cold_start_penalty_is_never_negative():
    """The schema requires >= 0, and a negative penalty has no meaning."""
    from aihwbench.metrics import cold_start_metrics

    for cold, warm in ((5.0, 50.0), (50.0, 5.0), (10.0, 10.0), (0.0, 1.0)):
        penalty = cold_start_metrics([{"load_time_ms": cold}], [{"load_time_ms": warm}])[
            "cold_start_penalty_ms"
        ]
        assert penalty is None or penalty >= 0
