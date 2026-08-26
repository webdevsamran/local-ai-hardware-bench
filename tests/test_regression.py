"""Tests for baseline/regression primitives."""

from __future__ import annotations

from aihwbench.regression import (
    RegressionThresholds,
    evaluate_regression,
)
from tests.test_ecosystem import _result


def test_pass_when_candidate_within_thresholds():
    base = _result("base", 100.0)
    cand = _result("cand", 95.0)  # 5% slower, within 10% budget
    report = evaluate_regression(base, cand)
    assert report.status == "PASS"
    assert report.failures == []


def test_fail_on_throughput_regression():
    base = _result("base", 100.0)
    cand = _result("cand", 80.0)  # 20% drop > 10% budget
    report = evaluate_regression(base, cand)
    assert report.status == "FAIL"
    assert any("generation_tokens_per_second" in f for f in report.failures)


def test_fail_on_ttft_increase():
    base = _result("base", 100.0)
    cand = _result("cand", 100.0)
    cand["metrics"]["ttft_ms"] = base["metrics"]["ttft_ms"] + 1000.0
    report = evaluate_regression(base, cand)
    assert report.status == "FAIL"
    assert any("ttft_ms" in f for f in report.failures)


def test_missing_metrics_are_skipped_not_failed():
    base = _result("base", 100.0)
    cand = _result("cand", 100.0)
    base["metrics"]["average_power_watts"] = None
    cand["metrics"]["average_power_watts"] = None
    report = evaluate_regression(base, cand)
    power = next(c for c in report.checks if c.metric == "average_power_watts")
    assert power.status == "SKIPPED"
    assert report.status == "PASS"


def test_incomparable_results_reported():
    base = _result("base", 100.0)
    cand = _result("cand", 100.0)
    cand["runtime"]["name"] = "llama.cpp"
    report = evaluate_regression(base, cand)
    assert report.status == "INCOMPARABLE"


def test_custom_thresholds_via_from_dict():
    t = RegressionThresholds.from_dict({"throughput_max_regression_pct": 1.0})
    base = _result("base", 100.0)
    cand = _result("cand", 98.0)  # 2% drop, fails 1% budget
    report = evaluate_regression(base, cand, t)
    assert report.status == "FAIL"


def test_machine_readable_output_shape():
    base = _result("base", 100.0)
    cand = _result("cand", 95.0)
    d = evaluate_regression(base, cand).to_dict()
    assert d["status"] in ("PASS", "FAIL", "INCOMPARABLE")
    assert isinstance(d["checks"], list)
    assert all("metric" in c and "status" in c for c in d["checks"])
