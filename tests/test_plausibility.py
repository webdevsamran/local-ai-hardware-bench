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
    """Rewritten to reach the check the way a real result does.

    This built `metrics.energy_joules_per_token` by hand, which no benchmark
    has ever produced -- the field was computed before power was measured and
    was null in every published result. So the test passed while the guard it
    covered never ran once on real data. It now goes through the `energy`
    block, where the figure actually lives.
    """
    findings = check_plausibility(
        {
            "system": {"gpu_vram_mb": 16384},
            "metrics": {"generation_tokens_per_second": 100.0},
            "energy": {
                "energy_joules_per_token": 99.0,  # should be about 0.5
                "incremental_power_watts": 50.0,
            },
        }
    )
    assert any(f["field"] == "energy.energy_joules_per_token" for f in findings)


def test_energy_within_rounding_tolerance_is_accepted():
    """0.5 J/token from 50 W incremental at 100 tok/s, with rounding."""
    assert (
        check_plausibility(
            {
                "system": {"gpu_vram_mb": 16384},
                "metrics": {"generation_tokens_per_second": 100.0},
                "energy": {
                    "energy_joules_per_token": 0.503,
                    "incremental_power_watts": 50.0,
                },
            }
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


def test_small_idle_excess_is_drift_not_a_finding():
    """Measured: 29.62 W idle against 28.26 W under load, a 4.6% excess.

    A 0.5B model held the GPU at ~6% utilization, so "average under load" was
    effectively a second idle sample -- and two idle samples on a laptop dGPU
    differ by a few percent as clocks and fans move. Calling that inconsistent
    put a manual-review flag on every result whose workload is not GPU-bound.
    """
    findings = check_plausibility(_result(idle_power_watts=29.62, average_power_watts=28.26))
    assert not any(f["field"] == "metrics.idle_power_watts" for f in findings)


def test_large_idle_excess_is_still_a_finding():
    """The structural case the check exists for is untouched."""
    findings = check_plausibility(_result(idle_power_watts=200.0, average_power_watts=50.0))
    flagged = [f for f in findings if f["field"] == "metrics.idle_power_watts"]
    assert flagged
    assert "300%" in flagged[0]["detail"]


# --- Energy per token must follow from the power it claims to come from -----
#
# This check read `metrics.energy_joules_per_token`, which is null in every
# result ever published: the field was computed inside
# `aggregate_iteration_metrics`, from a per-iteration power key no backend has
# ever set, and the telemetry that carries real power is merged only after
# that function returns. So the guard has never once run, in the one area
# where three separate energy defects have already been found.


def _energy_result(*, joules_per_token, incremental_watts, tps):
    return {
        "system": {"gpu_vram_mb": 16384},
        "metrics": {"generation_tokens_per_second": tps},
        "energy": {
            "energy_joules_per_token": joules_per_token,
            "incremental_power_watts": incremental_watts,
        },
    }


def test_energy_per_token_consistent_with_incremental_power_passes():
    # 22.08 W over 281.65 tok/s is 0.0784 J/token.
    findings = check_plausibility(
        _energy_result(joules_per_token=0.0784, incremental_watts=22.08, tps=281.65)
    )
    assert findings == []


def test_energy_per_token_that_does_not_follow_is_flagged():
    findings = check_plausibility(
        _energy_result(joules_per_token=5.0, incremental_watts=22.08, tps=281.65)
    )
    flagged = [f for f in findings if f["field"] == "energy.energy_joules_per_token"]
    assert flagged, "an energy figure inconsistent with its own inputs must be caught"
    assert "incremental" in flagged[0]["detail"]


def test_the_check_uses_incremental_power_not_gross():
    """Checking against gross would flag every correct result.

    The `energy` block computes per-token energy net of the machine's idle
    draw. A guard comparing that against gross power would fire on exactly the
    results that got it right, which is worse than not running at all.
    """
    result = _energy_result(joules_per_token=0.0784, incremental_watts=22.08, tps=281.65)
    # Gross power is much larger than incremental; its presence must not
    # change the verdict.
    result["metrics"]["average_power_watts"] = 53.32
    assert check_plausibility(result) == []


def test_no_energy_block_means_no_claim():
    findings = check_plausibility(_result(generation_tokens_per_second=281.65))
    assert not [f for f in findings if "energy" in f["field"]]


def test_metrics_no_longer_carries_a_field_it_cannot_compute():
    """The always-null duplicate is gone, not merely left null.

    A metric that is structurally impossible to populate reads as "not
    measured on this platform", which is a different and misleading claim.
    """
    from aihwbench.metrics import aggregate_iteration_metrics

    produced = aggregate_iteration_metrics(
        [{"completion_tokens": 100, "eval_seconds": 0.5, "total_latency_ms": 900.0}]
    )
    assert "energy_joules_per_token" not in produced
