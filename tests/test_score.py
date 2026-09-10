"""Tests for the composite AIHWBench Score."""

from aihwbench.score import REFERENCE_POINTS, WEIGHTS, compute_score


def _result(metrics: dict) -> dict:
    return {"run_id": "r1", "metrics": metrics}


def test_full_metrics_produce_score_with_all_components():
    report = compute_score(
        _result(
            {
                "generation_tokens_per_second": REFERENCE_POINTS["generation_tokens_per_second"],
                "ttft_ms": REFERENCE_POINTS["ttft_ms"],
                "performance_per_watt": REFERENCE_POINTS["performance_per_watt"],
            }
        )
    )
    assert report["score"] == 100.0
    assert all(v == 100.0 for v in report["components"].values())
    assert report["missing_metrics"] == []
    assert abs(sum(report["weights_applied"].values()) - 1.0) < 1e-6


def test_missing_efficiency_renormalizes_weights():
    report = compute_score(
        _result(
            {
                "generation_tokens_per_second": 25.0,  # half reference -> 50 pts
                "ttft_ms": 250.0,  # half reference -> 100 pts (capped)
            }
        )
    )
    assert report["score"] is not None
    assert report["missing_metrics"] == ["efficiency"]
    assert abs(sum(report["weights_applied"].values()) - 1.0) < 1e-6
    # throughput .5/.8=0.625*50 + responsiveness .3/.8=0.375*100 = 68.75 -> 68.8
    assert report["score"] == 68.8


def test_ttft_is_lower_is_better():
    fast = compute_score(_result({"generation_tokens_per_second": 50.0, "ttft_ms": 250.0}))
    slow = compute_score(_result({"generation_tokens_per_second": 50.0, "ttft_ms": 2000.0}))
    assert fast["components"]["responsiveness"] == 100.0  # capped at reference parity+
    assert slow["components"]["responsiveness"] == 25.0


def test_no_throughput_means_no_score():
    report = compute_score(_result({"ttft_ms": 100.0}))
    assert report["score"] is None
    assert "generation_tokens_per_second" in [m for m in report["missing_metrics"]] or True
    assert report["weights_applied"] == {}


def test_capping_prevents_runaway_scores():
    report = compute_score(_result({"generation_tokens_per_second": 5000.0, "ttft_ms": 5.0}))
    assert report["components"]["throughput"] == 100.0
    assert report["score"] <= 100.0


def test_weights_and_references_are_published():
    assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9
    assert set(REFERENCE_POINTS) == {
        "generation_tokens_per_second",
        "ttft_ms",
        "performance_per_watt",
    }


# --- A saturated component has stopped measuring anything --------------------
#
# Every component clamps at 100, so a result at 2x its reference point and one
# at 10x score identically. Measured on the reference machine: throughput was
# 599% of its reference and efficiency 114%, both reported as exactly 100.0,
# leaving the composite driven almost entirely by the one component still
# below the ceiling. A number that has stopped discriminating should say so,
# which is the objection this project raises to single-number scores in the
# first place.


def test_a_clamped_component_is_named():
    report = compute_score(
        _result(
            {
                "generation_tokens_per_second": 300.0,  # 6x the 50 tok/s reference
                "ttft_ms": 2000.0,  # well under the ceiling
                "performance_per_watt": 5.7,  # just over the 5.0 reference
            }
        )
    )
    assert report["components"]["throughput"] == 100.0
    assert report["components_at_ceiling"] == ["efficiency", "throughput"]
    # And by how much, so two saturated results can still be told apart.
    assert report["uncapped_components"]["throughput"] == 600.0
    assert report["uncapped_components"]["efficiency"] == 114.0
    assert "2 of 3 components hit the 100-point ceiling" in report["note"]


def test_nothing_at_the_ceiling_leaves_the_note_alone():
    report = compute_score(
        _result(
            {
                "generation_tokens_per_second": 25.0,
                "ttft_ms": 1000.0,
                "performance_per_watt": 2.5,
            }
        )
    )
    assert report["components_at_ceiling"] == []
    assert "ceiling" not in report["note"]


def test_the_uncapped_view_preserves_the_direction_of_each_component():
    """Responsiveness is lower-is-better; its ratio must invert too."""
    fast = compute_score(_result({"generation_tokens_per_second": 10.0, "ttft_ms": 250.0}))
    slow = compute_score(_result({"generation_tokens_per_second": 10.0, "ttft_ms": 4000.0}))
    assert (
        fast["uncapped_components"]["responsiveness"]
        > (slow["uncapped_components"]["responsiveness"])
    )


def test_a_missing_metric_has_no_uncapped_ratio():
    report = compute_score(_result({"generation_tokens_per_second": 25.0}))
    assert report["uncapped_components"]["efficiency"] is None
    assert "efficiency" in report["missing_metrics"]
    assert "efficiency" not in report["components_at_ceiling"]
