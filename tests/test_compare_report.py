"""Tests for comparison and report generation."""

from aihwbench.compare import comparability_warnings, compare_results, render_comparison
from aihwbench.report import render_report
from tests.test_schemas import make_valid_result


def _result(run_id: str, gen_tps: float) -> dict:
    result = make_valid_result()
    result["run_id"] = run_id
    result["metrics"]["generation_tokens_per_second"] = gen_tps
    return result


def test_comparable_results_have_no_warnings():
    a = _result("a", 40.0)
    b = _result("b", 50.0)
    assert comparability_warnings(a, b) == []


def test_different_models_warn():
    a = _result("a", 40.0)
    b = _result("b", 50.0)
    b["model"]["name"] = "other-model"
    warnings = comparability_warnings(a, b)
    assert any("models differ" in w for w in warnings)


def test_compare_results_deltas():
    a = _result("a", 40.0)
    b = _result("b", 50.0)
    comparison = compare_results(a, b)
    row = next(r for r in comparison["metrics"] if r["metric"] == "generation_tokens_per_second")
    assert row["delta_percent"] == 25.0


def test_render_comparison_contains_table():
    text = render_comparison(compare_results(_result("a", 40.0), _result("b", 50.0)))
    assert "| Metric |" in text
    assert "generation_tokens_per_second" in text


def test_render_report_contains_sections():
    text = render_report(make_valid_result())
    assert "# Benchmark Report" in text
    assert "## Metrics" in text
    assert "## Reproducibility" in text
    assert "not measured" in text  # null metrics are explicit, never hidden
