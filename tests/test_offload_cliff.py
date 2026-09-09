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
