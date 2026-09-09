"""Impossible and self-contradictory values in submitted results.

The moment a leaderboard matters, someone tries to top it. These checks are
deliberately the uncontroversial half of defending against that: they assert
only what is impossible or internally inconsistent, never what hardware is
capable of. A false accusation costs far more than a missed one.

Every finding is a review request. The likeliest cause of an impossible value
is a measurement bug, which is worth finding on its own merits.
"""

from __future__ import annotations

import glob
import json

import pytest

from aihwbench.plausibility import check_plausibility


def _result(**metrics) -> dict:
    return {"system": {"gpu_vram_mb": 16384}, "metrics": metrics}


@pytest.mark.parametrize("path", sorted(glob.glob("results/published/*.json")))
def test_no_published_result_is_implausible(path):
    """No false positives on real data, or the check is worthless."""
    findings = check_plausibility(json.loads(open(path, encoding="utf-8").read()))
    assert findings == [], f"{path}: {findings}"


def test_a_run_cannot_use_more_vram_than_the_card_has():
    findings = check_plausibility(_result(peak_vram_mb=40000))
    assert any(f["field"] == "metrics.peak_vram_mb" for f in findings)


def test_using_exactly_all_the_vram_is_allowed():
    """A boundary, not a violation: a full card is a real measurement."""
    assert check_plausibility(_result(peak_vram_mb=16384)) == []


def test_the_first_token_cannot_arrive_after_the_last():
    findings = check_plausibility(_result(ttft_ms=900, total_latency_ms=400))
    assert any("exceeds total latency" in f["detail"] for f in findings)


def test_percentiles_cannot_decrease():
    findings = check_plausibility(_result(p50_latency_ms=300, p95_latency_ms=100))
    assert any(f["field"] == "metrics.p95_latency_ms" for f in findings)
    assert any(f["kind"] == "inconsistent" for f in findings)


def test_percentiles_may_be_equal():
    """Identical percentiles mean low spread, not a contradiction."""
    assert check_plausibility(_result(p50_latency_ms=100, p95_latency_ms=100)) == []


@pytest.mark.parametrize("value", [-1.0, -0.001])
def test_negative_metrics_are_impossible(value):
    findings = check_plausibility(_result(generation_tokens_per_second=value))
    assert any(f["kind"] == "impossible" for f in findings)


@pytest.mark.parametrize("value", [-5.0, 101.0, 130.0])
def test_utilisation_outside_zero_to_one_hundred(value):
    findings = check_plausibility(_result(avg_gpu_util_percent=value))
    assert any(f["field"] == "metrics.avg_gpu_util_percent" for f in findings)


@pytest.mark.parametrize("value", [0.0, 50.0, 100.0])
def test_utilisation_within_range_is_fine(value):
    assert check_plausibility(_result(avg_gpu_util_percent=value)) == []


def test_a_hot_laptop_is_not_flagged():
    """95 C is a real reading under load; the bound must not catch it."""
    assert check_plausibility(_result(max_temperature_c=95.0)) == []


def test_an_impossible_temperature_is_flagged():
    findings = check_plausibility(_result(max_temperature_c=900.0))
    assert any(f["field"] == "metrics.max_temperature_c" for f in findings)


def test_idle_power_above_load_power_is_inconsistent():
    findings = check_plausibility(_result(idle_power_watts=200.0, average_power_watts=50.0))
    assert any(f["field"] == "metrics.idle_power_watts" for f in findings)


def test_energy_per_token_must_follow_from_power_and_throughput():
    findings = check_plausibility(
        _result(
            average_power_watts=50.0,
            generation_tokens_per_second=100.0,
            energy_joules_per_token=99.0,  # should be about 0.5
        )
    )
    assert any(f["field"] == "metrics.energy_joules_per_token" for f in findings)


def test_energy_within_rounding_tolerance_is_accepted():
    """0.5 J/token from 50 W at 100 tok/s, with rounding."""
    assert (
        check_plausibility(
            _result(
                average_power_watts=50.0,
                generation_tokens_per_second=100.0,
                energy_joules_per_token=0.503,
            )
        )
        == []
    )


def test_missing_metrics_are_not_findings():
    """Absence is not implausibility; unmeasured is a normal state here."""
    assert check_plausibility({"metrics": {}, "system": {}}) == []
    assert check_plausibility({}) == []


def test_findings_request_review_rather_than_alleging_fraud():
    findings = check_plausibility(_result(peak_vram_mb=40000))
    assert findings
    for finding in findings:
        assert finding["action"] == "manual_review"


def test_no_performance_ceiling_is_asserted():
    """A very fast but possible result must not be flagged.

    'A card cannot exceed N tok/s' is a claim about hardware this project has
    not measured across the range. Statistical outliers are caught by cohort
    comparison in quality.flag_anomalies, not by a guessed bound.
    """
    assert check_plausibility(_result(generation_tokens_per_second=5000.0)) == []
