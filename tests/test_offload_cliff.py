"""The offload cliff, and the KV-cache axis.

The largest performance discontinuity in local inference is the point at
which a model stops fitting in VRAM: throughput does not taper, it collapses.
Where that happens depends on the machine, which makes it the question a
crowdsourced benchmark can answer and a vendor one cannot.
"""

from __future__ import annotations

import pytest

from aihwbench.analysis.cliff import find_offload_cliff


def _point(layers, tps):
    return {"params": {"gpu_layers": layers}, "metrics": {"generation_tokens_per_second": tps}}


def test_finds_the_cliff_between_adjacent_configurations():
    # Flat while resident, collapsing once layers spill to the CPU.
    report = find_offload_cliff(
        [_point(0, 6.2), _point(16, 9.8), _point(24, 14.1), _point(32, 41.7), _point(99, 43.0)]
    )
    assert report["cliff_detected"] is True
    assert report["cliff_between_layers"] == [24.0, 32.0]
    assert report["best_layers"] == 99.0
    assert report["best_tokens_per_second"] == 43.0


def test_reports_the_slowdown_a_user_would_feel():
    report = find_offload_cliff([_point(24, 14.1), _point(32, 41.7)])
    drop = report["drops"][0]
    assert drop["slowdown_factor"] == pytest.approx(2.957, abs=0.001)


def test_smooth_scaling_is_not_a_cliff():
    report = find_offload_cliff([_point(0, 40.0), _point(16, 44.0), _point(32, 48.0)])
    assert report["cliff_detected"] is False


def test_a_single_point_cannot_show_a_cliff():
    """A cliff is a drop between configurations; one point has no neighbour."""
    report = find_offload_cliff([_point(32, 40.0)])
    assert report["cliff_detected"] is None
    assert "at least two measured points" in report["reason"]


def test_unmeasured_points_are_excluded_not_treated_as_zero():
    """A failed run is missing data, not a throughput of zero."""
    report = find_offload_cliff([_point(32, 40.0), _point(16, None), _point(0, 5.0)])
    assert report["points"] == 2
    assert report["excluded_missing_data"] == 1


def test_rows_without_the_axis_are_excluded():
    report = find_offload_cliff(
        [_point(32, 40.0), {"params": {}, "metrics": {"generation_tokens_per_second": 9.0}}]
    )
    assert report["excluded_missing_data"] == 1


# ------------------------------------------------------------- KV cache axis


def test_llama_cpp_accepts_asymmetric_kv_cache_types():
    """K and V tolerate quantization differently, so they are set separately."""
    from aihwbench.backends.base import BenchmarkConfig
    from aihwbench.backends.llama_cpp import _cache_type

    config = BenchmarkConfig(model="m", extra={"cache_type_k": "q8_0", "cache_type_v": "q4_0"})
    assert _cache_type(config, "k") == "q8_0"
    assert _cache_type(config, "v") == "q4_0"


def test_unset_kv_cache_type_stays_unset():
    """Absent means 'llama.cpp default', not a value this project chose."""
    from aihwbench.backends.base import BenchmarkConfig
    from aihwbench.backends.llama_cpp import _cache_type

    assert _cache_type(BenchmarkConfig(model="m"), "k") is None


def test_unknown_kv_cache_type_is_refused_before_the_server_starts():
    from aihwbench.backends import BackendError
    from aihwbench.backends.base import BenchmarkConfig
    from aihwbench.backends.llama_cpp import _cache_type

    with pytest.raises(BackendError, match="unknown KV cache type"):
        _cache_type(BenchmarkConfig(model="m", extra={"cache_type_k": "q3_k_m"}), "k")


def test_kv_cache_axes_are_declared_as_tunable():
    from aihwbench.backends import backend_tunable_axes

    axes = backend_tunable_axes("llama.cpp")
    assert "cache_type_k" in axes and "cache_type_v" in axes


# ------------------------------------------------------- context scaling
#
# A run at one context length is a single point on a curve, and usually the
# flattering one. Prefill cost and KV cache both grow with input length, and
# where a machine falls off is what someone needs before committing to a
# long-prompt workflow.


def _ctx(tokens, ttft=None, tps=None, vram=None):
    return {
        "params": {"context_length": tokens},
        "metrics": {
            "ttft_ms": ttft,
            "generation_tokens_per_second": tps,
            "peak_vram_mb": vram,
        },
    }


def test_superlinear_prefill_is_flagged():
    """Attention is quadratic; the flag marks where that stops being a detail."""
    from aihwbench.analysis.context import analyze_context_scaling

    # 16x the context for 60x the TTFT.
    report = analyze_context_scaling([_ctx(4096, ttft=120), _ctx(65536, ttft=7200)])
    prefill = report["prefill_scaling"]
    assert prefill["superlinear"] is True
    assert prefill["superlinearity"] == pytest.approx(3.75, abs=0.01)


def test_linear_prefill_is_not_flagged():
    """Doubling context for double the prefill is the expected case."""
    from aihwbench.analysis.context import analyze_context_scaling

    report = analyze_context_scaling([_ctx(4096, ttft=100), _ctx(8192, ttft=200)])
    assert report["prefill_scaling"]["superlinear"] is False


def test_memory_saturation_is_found_and_explained():
    """VRAM that stops growing usually means spilling, not sufficiency."""
    from aihwbench.analysis.context import analyze_context_scaling

    report = analyze_context_scaling(
        [_ctx(4096, vram=4000), _ctx(8192, vram=8000), _ctx(16384, vram=8010)]
    )
    assert report["memory_saturation_tokens"] == 16384
    assert "spilling" in report["memory_saturation_note"]


def test_last_usable_depth_respects_the_caller_s_floor():
    from aihwbench.analysis.context import analyze_context_scaling

    report = analyze_context_scaling(
        [_ctx(4096, tps=45.0), _ctx(16384, tps=38.0), _ctx(65536, tps=6.0)],
        min_acceptable_tps=20.0,
    )
    assert report["last_usable_context_tokens"] == 16384


def test_no_depth_meets_an_impossible_floor():
    from aihwbench.analysis.context import analyze_context_scaling

    report = analyze_context_scaling([_ctx(4096, tps=45.0)], min_acceptable_tps=1000.0)
    assert report["last_usable_context_tokens"] is None


def test_a_single_depth_is_not_a_curve():
    from aihwbench.analysis.context import analyze_context_scaling

    report = analyze_context_scaling([_ctx(4096, ttft=100)])
    assert report["prefill_scaling"] is None
    assert "cannot be drawn through one point" in report["reason"]


def test_context_rows_without_the_axis_are_excluded():
    from aihwbench.analysis.context import analyze_context_scaling

    report = analyze_context_scaling(
        [_ctx(4096, ttft=100), {"params": {}, "metrics": {"ttft_ms": 200}}, _ctx(8192, ttft=200)]
    )
    assert report["points"] == 2
    assert report["excluded_missing_axis"] == 1


def test_nothing_is_extrapolated_to_unmeasured_depths():
    """The curve exists because it cannot be predicted from one point."""
    from aihwbench.analysis.context import analyze_context_scaling

    report = analyze_context_scaling([_ctx(4096, tps=40.0), _ctx(8192, tps=35.0)])
    measured = {p["context_tokens"] for p in report["curve"]}
    assert measured == {4096, 8192}


# --- The "best" setting must be one the data can actually distinguish -------
#
# `best_layers` was a bare max() over the measured means, which names a winner
# whenever one mean is highest, however marginally. Measured on the reference
# machine at 3 iterations per point: 247.06 tok/s at 24 GPU layers and 222.8
# at 99 — a 10% gap that vanished at 6 iterations, where 99 won decisively
# with non-overlapping intervals. Advising someone to pin --gpu-layers 24 on
# the strength of the first sweep would have been tuning against noise.


def _point_ci(layers, tps, ci):
    return {
        "params": {"gpu_layers": layers},
        "metrics": {"generation_tokens_per_second": tps, "gen_tps_ci95": list(ci)},
    }


def test_best_setting_reports_what_it_cannot_be_told_apart_from():
    report = find_offload_cliff(
        [
            _point_ci(0, 42.0, (32.0, 52.0)),
            _point_ci(24, 281.85, (268.7, 295.0)),
            # Overlaps the 24-layer interval: not distinguishable.
            _point_ci(99, 288.0, (270.0, 306.0)),
        ]
    )
    assert report["best_layers"] == 99
    assert report["best_is_tied_with"] == [24]
    assert "confidence intervals" in report["tie_basis"]


def test_a_decisive_best_reports_no_ties():
    """The measured 6-iteration sweep: 99 layers beat 24 outright."""
    report = find_offload_cliff(
        [
            _point_ci(18, 137.22, (125.11, 149.32)),
            _point_ci(24, 281.85, (268.71, 294.98)),
            _point_ci(99, 349.45, (331.06, 367.83)),
        ]
    )
    assert report["best_layers"] == 99
    assert report["best_is_tied_with"] == []


def test_falls_back_to_a_margin_when_no_interval_was_measured():
    """Older sweeps carry no intervals; silence would read as "nothing close"."""
    report = find_offload_cliff(
        [
            _point(0, 35.01),
            _point(24, 247.06),
            _point(99, 222.8),  # within 10% of the best
        ]
    )
    assert report["best_layers"] == 24
    assert report["best_is_tied_with"] == [99]
    # The weaker test is labelled as weaker rather than passed off as the same
    # claim: "within 10%" and "statistically indistinguishable" differ.
    assert "no interval measured" in report["tie_basis"]


def test_a_clearly_slower_point_is_not_called_a_tie():
    report = find_offload_cliff([_point(0, 35.0), _point(99, 350.0)])
    assert report["best_layers"] == 99
    assert report["best_is_tied_with"] == []


# --- The published sweep ----------------------------------------------------


def test_the_published_sweep_still_shows_its_cliff():
    """Guards the artifact docs/results/offload-cliff-rtx3080ti.md describes.

    A published measurement that silently stops parsing, or whose analysis
    stops finding what the write-up claims, is a citation pointing at nothing.
    """
    import json
    import pathlib

    path = (
        pathlib.Path(__file__).resolve().parent.parent
        / "results"
        / "sweeps"
        / "sweep-llama.cpp.json"
    )
    sweep = json.loads(path.read_text(encoding="utf-8"))

    # The environment is what makes the curve interpretable elsewhere: an
    # offload cliff is a property of this GPU's memory and link as much as of
    # the model.
    environment = sweep["environment"]
    assert environment["model"], "a cliff curve with no model attached says nothing"
    assert environment["system"]["gpu"]
    assert environment["runtime"] == "llama.cpp"

    report = find_offload_cliff(sweep["matrix"])
    assert report["cliff_detected"] is True
    assert report["excluded_missing_data"] == 0
    assert report["cliff_between_layers"] == [18.0, 24.0]
    # Every point carries the interval the tie check needs.
    assert report["tie_basis"] == "overlapping 95% confidence intervals"
    assert report["best_layers"] == 99.0
