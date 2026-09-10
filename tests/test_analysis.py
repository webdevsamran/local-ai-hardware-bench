"""Tests for evaluators, analysis engines, quantization comparison, tuner."""

from __future__ import annotations

import pytest

from aihwbench.analysis import (
    analyze_bottlenecks,
    compute_cost_metrics,
    compute_energy_metrics,
    estimate_model_fit,
    recommend_configuration,
)
from aihwbench.analysis.thermal import analyze_thermal_stability
from aihwbench.analysis.tune import UnsupportedAxisError, run_tuner
from aihwbench.evaluators import (
    CosineSimilarityEvaluator,
    ExactMatchEvaluator,
    JsonValidityEvaluator,
    get_evaluator,
    list_evaluators,
    load_dataset,
    run_evaluation,
)
from aihwbench.quantization import compare_quantizations, performance_quality_frontier

# ---------------------------------------------------------------------------
# Evaluators
# ---------------------------------------------------------------------------


def test_exact_match_normalizes_whitespace():
    ev = ExactMatchEvaluator()
    assert ev.evaluate("hello  world", "hello world").score == 1.0
    assert ev.evaluate("hello there", "hello world").score == 0.0
    assert ev.evaluate("anything", None).score is None


def test_json_validity():
    ev = JsonValidityEvaluator()
    assert ev.evaluate('{"a": 1}').score == 1.0
    assert ev.evaluate("not json {").score == 0.0


def test_cosine_similarity_math():
    ev = CosineSimilarityEvaluator()
    assert ev.evaluate_vectors([1.0, 0.0], [1.0, 0.0]).score == pytest.approx(1.0)
    assert ev.evaluate_vectors([1.0, 0.0], [0.0, 1.0]).score == pytest.approx(0.0)
    assert ev.evaluate_vectors([1.0], [1.0, 2.0]).score is None
    assert ev.evaluate_vectors([0.0, 0.0], [1.0, 0.0]).score is None


def test_registry_and_unknown_evaluator():
    names = list_evaluators()
    for expected in ("exact_match", "json_validity", "embedding_cosine"):
        assert expected in names
    with pytest.raises(KeyError):
        get_evaluator("no_such_evaluator")


def test_run_evaluation_mean_is_none_without_scores():
    report = run_evaluation("exact_match", ["a", "b"], [None, None])
    assert report["mean_score"] is None
    assert report["scored_items"] == 0


def test_run_evaluation_scores_items():
    report = run_evaluation("exact_match", ["yes", "no", " yes "], ["yes", "yes", "yes"])
    assert report["mean_score"] == pytest.approx(2 / 3)


def test_load_dataset_validates_lines(tmp_path):
    path = tmp_path / "ds.jsonl"
    nl = chr(10)
    path.write_text(
        '{"input": "q", "expected": "a"}' + nl + '{"input": "q2"}' + nl,
        encoding="utf-8",
    )
    items = load_dataset(path)
    assert len(items) == 2
    bad = tmp_path / "bad.jsonl"
    bad.write_text('{"no_input": true}' + chr(10), encoding="utf-8")
    with pytest.raises(ValueError):
        load_dataset(bad)


def test_evaluator_plugin_registration():
    from aihwbench.evaluators import register_evaluator

    class Upper(ExactMatchEvaluator):
        name = "test_upper_plugin"

    register_evaluator(Upper())
    assert "test_upper_plugin" in list_evaluators()


# ---------------------------------------------------------------------------
# Fit estimator
# ---------------------------------------------------------------------------


def test_fit_estimate_known_quantization():
    out = estimate_model_fit("7B", "q4_k_m", available_vram_mb=8000)
    # 7e9 * 4.85/8 bytes = ~4.24 GB weights; x1.15 overhead = ~4.88 GB.
    assert out["estimated_weights_gb"] == pytest.approx(4.24, abs=0.05)
    assert out["fits"] is True
    assert out["assumptions"]["bits_per_weight"] == 4.85


def test_fit_refuses_unknown_quantization():
    out = estimate_model_fit("7B", "mystery_quant")
    assert out["fits"] is None
    assert "refusing" in out["reason"]


def test_fit_requires_parameter_count():
    out = estimate_model_fit(None, "fp16")
    assert out["estimated_total_gb"] is None


def test_parse_parameter_count_units():
    assert estimate_model_fit.__module__  # sanity
    from aihwbench.analysis.fit import parse_parameter_count

    assert parse_parameter_count("7B") == 7e9
    assert parse_parameter_count("350M") == 350e6
    assert parse_parameter_count("llama-3.2-1b-instruct") == 1e9
    assert parse_parameter_count(None) is None


# ---------------------------------------------------------------------------
# Bottleneck analyzer
# ---------------------------------------------------------------------------


def test_bottleneck_gpu_compute_detected():
    findings = analyze_bottlenecks({"avg_gpu_util_percent": 96.0})
    kinds = [f["bottleneck"] for f in findings]
    assert "gpu_compute" in kinds
    assert all("rule" in f and "evidence" in f for f in findings)


def test_bottleneck_no_findings_without_telemetry():
    assert analyze_bottlenecks({}) == []


def test_bottleneck_vram_capacity_rule():
    findings = analyze_bottlenecks({"peak_vram_mb": 7900.0}, {"gpu_vram_mb": 8192})
    assert any(f["bottleneck"] == "vram_capacity" for f in findings)


def test_bottleneck_thermal_rule():
    findings = analyze_bottlenecks({"max_temperature_c": 91.0})
    assert any(f["bottleneck"] == "thermal" for f in findings)


# ---------------------------------------------------------------------------
# Thermal stability
# ---------------------------------------------------------------------------


def test_thermal_stability_measures_degradation_and_throttle():
    t = [float(i) for i in range(10)]
    tps = [100.0] * 5 + [90.0, 85.0, 82.0, 80.0, 80.0]
    temps = [60.0 + i * 3.0 for i in range(10)]  # crosses 85 at i=9 (87C)
    out = analyze_thermal_stability(t, tps, temps)
    assert out["peak_throughput_tps"] == 100.0
    assert out["steady_state_throughput_tps"] == pytest.approx(sum(tps[-5:]) / 5)
    assert out["degradation_percent"] == pytest.approx(16.6, abs=0.01)
    assert out["time_to_throttle_s"] == 9.0
    assert len(out["temperature_curve"]) == 10


def test_thermal_insufficient_samples_is_none_not_zero():
    out = analyze_thermal_stability([], [], [])
    assert out["peak_throughput_tps"] is None
    assert "insufficient" in out["reason"]


def test_thermal_rejects_unordered_timestamps():
    with pytest.raises(ValueError):
        analyze_thermal_stability([5.0, 1.0], [1.0, 2.0], [50.0, 51.0])


# ---------------------------------------------------------------------------
# Energy and cost
# ---------------------------------------------------------------------------


def test_energy_metrics_incremental_power():
    out = compute_energy_metrics(
        average_power_watts=120.0,
        idle_power_watts=20.0,
        generation_tokens_per_second=40.0,
        requests_per_second=2.0,
        telemetry_source="nvidia-smi",
    )
    assert out["incremental_power_watts"] == 100.0
    assert out["energy_joules_per_token"] == pytest.approx(2.5)
    assert out["energy_joules_per_request"] == pytest.approx(50.0)
    assert out["energy_joules_per_1k_tokens"] == pytest.approx(2500.0)
    assert out["telemetry_source"] == "nvidia-smi"


def test_energy_metrics_none_without_inputs():
    out = compute_energy_metrics(None, None, None, None)
    assert out["energy_joules_per_token"] is None
    assert out["incremental_power_watts"] is None


def test_cost_metrics_user_supplied_only():
    out = compute_cost_metrics(
        hardware_cost_usd=1000.0,
        electricity_usd_per_kwh=0.15,
        average_power_watts=100.0,
        generation_tokens_per_second=50.0,
        utilization_hours_per_day=12.0,
        years=3,
    )
    assert out["tokens_per_dollar"] is not None
    assert out["energy_cost_per_1k_tokens_usd"] is not None
    assert out["tco"]["total_usd"] > 1000.0
    assert out["inputs"]["electricity_usd_per_kwh"] == 0.15


def test_cost_metrics_empty_without_inputs():
    out = compute_cost_metrics()
    assert out["tokens_per_dollar"] is None
    assert out["tco"] is None


# ---------------------------------------------------------------------------
# Recommendation engine
# ---------------------------------------------------------------------------


def test_recommend_estimated_tier_without_measurements():
    system = {"gpu_vram_mb": 8192, "ram_gb": 32}
    rec = recommend_configuration(system)
    assert rec["evidence_tier"] == "estimated"
    assert rec["recommended_model_parameters_b"] is not None
    assert rec["recommended_device"] == "gpu"
    assert rec["uncertainty"]
    assert rec["reasons"]


def test_recommend_measured_tier_with_results():
    results = [
        {
            "runtime": {"name": "ollama", "device": "cuda"},
            "metrics": {"generation_tokens_per_second": 30.0},
        },
        {
            "runtime": {"name": "llama.cpp", "device": "cpu"},
            "metrics": {"generation_tokens_per_second": 55.0},
        },
    ]
    rec = recommend_configuration({"gpu_vram_mb": 6144, "ram_gb": 16}, results)
    assert rec["evidence_tier"] == "measured"
    assert rec["recommended_runtime"] == "llama.cpp"


# ---------------------------------------------------------------------------
# Quantization comparison + frontier
# ---------------------------------------------------------------------------


def _result(run_id: str, model: str, quant: str, tps: float | None, score: float | None):
    return {
        "run_id": run_id,
        "model": {"name": model, "quantization": quant},
        "metrics": {"generation_tokens_per_second": tps},
        "quality": {"mean_score": score} if score is not None else None,
    }


def test_compare_quantizations_groups_by_family():
    results = [
        _result("r1", "llama-3.2-1b-q4_k_m", "Q4_K_M", 45.0, None),
        _result("r2", "llama-3.2-1b-fp16", "FP16", 30.0, None),
        _result("r3", "qwen2-0.5b-q8", "Q8_0", 80.0, None),
    ]
    out = compare_quantizations(results)
    assert set(out["families"]) == {"llama", "qwen2"}
    llama_rows = out["families"]["llama"]
    assert {r["quantization"] for r in llama_rows} == {"Q4_K_M", "FP16"}
    assert llama_rows[0]["generation_tokens_per_second"] == 45.0


def test_frontier_excludes_missing_data_and_finds_pareto():
    results = [
        _result("fast_dumb", "m-q4", "Q4", 100.0, 0.5),
        _result("slow_smart", "m-fp16", "FP16", 40.0, 0.95),
        _result("dominated", "m-q2", "Q2", 50.0, 0.4),
        _result("no_quality", "m-q8", "Q8", 70.0, None),
    ]
    out = performance_quality_frontier(results)
    ids = {p["run_id"] for p in out["frontier"]}
    assert ids == {"fast_dumb", "slow_smart"}
    assert out["excluded_missing_data"] == 1


# ---------------------------------------------------------------------------
# Auto-tuner
# ---------------------------------------------------------------------------


def test_tuner_classifies_verdicts_from_measured_points():
    def run_fn(point: dict) -> dict:
        threads = point["threads"]
        return {
            "run_id": f"t{threads}",
            "metrics": {
                "generation_tokens_per_second": float(threads * 10),
                "peak_vram_mb": float(4000 - threads * 100),
            },
        }

    report = run_tuner({"threads": (1, 2, 4)}, run_fn)
    assert report["points_measured"] == 3
    assert report["fastest"]["run_id"] == "t4"
    assert report["lowest_memory"]["run_id"] == "t4"
    assert report["most_efficient"] is None  # no power measured -> honest null
    assert isinstance(report["balanced_frontier"], list)


def test_tuner_default_axes_when_empty():
    calls: list[dict] = []

    def run_fn(point: dict) -> dict:
        calls.append(point)
        return {"run_id": "x", "metrics": {"generation_tokens_per_second": 1.0}}

    report = run_tuner({}, run_fn)
    assert report["points_measured"] == len(calls) == 4  # default threads axis


# ---------------------------------------------------------------------------
# Tuner axis support
#
# The tuner used to sweep `threads`, `batch_size`, `gpu_layers` and
# `concurrency` while no backend read any of them: the values reached
# BenchmarkConfig.extra and were dropped. Every point ran the identical
# benchmark, so the "fastest" verdict was whichever repeat happened to win on
# noise -- reported to the user as an optimal configuration, citing measured
# values. A tuner that cannot vary something must refuse, not measure noise.


def test_tuner_refuses_an_axis_the_backend_does_not_apply():
    def run_fn(_point):
        raise AssertionError("must refuse before running any benchmark")

    with pytest.raises(UnsupportedAxisError) as excinfo:
        run_tuner(
            {"threads": (1, 2, 4)},
            run_fn,
            supported_axes=("gpu_layers",),
            runtime="llama.cpp",
        )
    message = str(excinfo.value)
    assert "threads" in message
    assert "gpu_layers" in message, "the error must name what IS supported"


def test_tuner_runs_when_every_axis_is_supported():
    def run_fn(point):
        return {"metrics": {"generation_tokens_per_second": float(point["gpu_layers"])}}

    report = run_tuner(
        {"gpu_layers": (0, 99)},
        run_fn,
        supported_axes=("gpu_layers", "context_length"),
        runtime="llama.cpp",
    )
    assert report["points_measured"] == 2
    assert report["fastest"]["params"]["gpu_layers"] == 99


def test_tuner_without_declared_support_is_unchecked():
    """Callers that pass no support list keep the old permissive behaviour."""

    def run_fn(_point):
        return {"metrics": {"generation_tokens_per_second": 1.0}}

    assert run_tuner({"threads": (1, 2)}, run_fn)["points_measured"] == 2


def test_llama_cpp_declares_and_applies_gpu_layers():
    """The axis the tuner offers must reach the spawned server command."""
    from aihwbench.backends import backend_tunable_axes
    from aihwbench.backends.base import BenchmarkConfig
    from aihwbench.backends.llama_cpp import _gpu_layers

    assert "gpu_layers" in backend_tunable_axes("llama.cpp")
    for requested in (0, 16, 99):
        config = BenchmarkConfig(model="m", device="cuda", extra={"gpu_layers": requested})
        assert _gpu_layers(config) == requested


def test_llama_cpp_gpu_layers_default_is_unchanged():
    """Absent an explicit value, the historical default still applies."""
    from aihwbench.backends.base import BenchmarkConfig
    from aihwbench.backends.llama_cpp import _gpu_layers

    assert _gpu_layers(BenchmarkConfig(model="m", device="cuda")) == 99
    assert _gpu_layers(BenchmarkConfig(model="m", device="cpu")) == 0


# ---------------------------------------------------------------------------
# Telemetry trace, and the analyzers it finally gives a producer
#
# analyze_thermal_stability and compute_energy_metrics were called only from
# tests: nothing published the time series they consume, so neither could run
# against a real benchmark. The trace is now part of the telemetry block and
# the runner attaches both analyses.


def test_trace_series_reads_a_published_trace():
    from aihwbench.telemetry import trace_series

    result = {
        "telemetry": {
            "trace": {"series": [{"timestamp": 1.0, "temperature_c": 60.0}]},
        }
    }
    assert len(trace_series(result)) == 1


@pytest.mark.parametrize(
    "result",
    [
        {},
        {"telemetry": None},
        {"telemetry": "not-an-object"},
        {"telemetry": {}},
        {"telemetry": {"trace": None}},
        {"telemetry": {"trace": {"series": "not-a-list"}}},
    ],
)
def test_trace_series_reports_nothing_rather_than_inventing(result):
    """Results written before traces existed must not crash an analyzer."""
    from aihwbench.telemetry import trace_series

    assert trace_series(result) == []


def test_thermal_from_trace_measures_the_throttle_point():
    from aihwbench.analysis.thermal import thermal_from_trace

    # Rising 1.5 C per sample, one sample per second, from 60 C.
    series = [{"timestamp": 1000.0 + i, "temperature_c": 60.0 + i * 1.5} for i in range(20)]
    report = thermal_from_trace(series, throttle_temp_c=85.0)
    assert report["throttled"] is True
    assert report["time_to_throttle_s"] == 17.0
    assert report["max_temperature_c"] == 88.5
    assert report["temperature_slope_c_per_min"] == 90.0


def test_thermal_from_trace_reports_no_throttle_when_cool():
    from aihwbench.analysis.thermal import thermal_from_trace

    series = [{"timestamp": 1000.0 + i, "temperature_c": 55.0} for i in range(10)]
    report = thermal_from_trace(series)
    assert report["throttled"] is False
    assert report["time_to_throttle_s"] is None


def test_thermal_from_trace_declines_without_enough_samples():
    from aihwbench.analysis.thermal import thermal_from_trace

    report = thermal_from_trace([{"timestamp": 1.0, "temperature_c": 60.0}])
    assert report["temperature_slope_c_per_min"] is None
    assert "fewer than two" in report["reason"]


def test_thermal_from_trace_never_invents_throughput():
    """A trace has no per-sample throughput; the fields must stay null."""
    from aihwbench.analysis.thermal import thermal_from_trace

    series = [{"timestamp": float(i), "temperature_c": 60.0 + i} for i in range(10)]
    report = thermal_from_trace(series)
    assert report["peak_throughput_tps"] is None
    assert report["steady_state_throughput_tps"] is None
    assert report["degradation_percent"] is None
    assert "sustained-load protocol" in report["reason"]


def test_trace_is_downsampled_rather_than_truncated():
    """The tail is where throttling shows, so it must survive downsampling."""
    from aihwbench.telemetry import TelemetrySampler

    sampler = TelemetrySampler(interval_seconds=0.01)
    sampler._samples = [  # noqa: SLF001 - constructing a known series
        {"timestamp": float(i), "temperature_c": float(i)} for i in range(100)
    ]
    trace = sampler.trace_for_result(max_samples=10)
    assert trace["samples_total"] == 100
    assert trace["samples_kept"] == 10
    assert trace["downsampled"] is True
    assert trace["series"][0]["timestamp"] == 0.0
    assert trace["series"][-1]["timestamp"] == 99.0


def test_short_traces_are_published_whole():
    from aihwbench.telemetry import TelemetrySampler

    sampler = TelemetrySampler(interval_seconds=0.01)
    sampler._samples = [{"timestamp": float(i)} for i in range(5)]  # noqa: SLF001
    trace = sampler.trace_for_result(max_samples=10)
    assert trace["downsampled"] is False
    assert trace["samples_kept"] == 5


# ---------------------------------------------------------------------------
# The recommender must agree with the fit estimator
#
# It sized weights against the whole memory budget while the fit check applied
# a 1.15x overhead factor, so the two disagreed: for a 24 GB card it proposed
# 36.5B parameters and then reported that this needed 25.4 GB and fitted only
# against system RAM. A recommendation that fails the project's own fit check
# is worse than no recommendation.


@pytest.mark.parametrize(
    ("vram_mb", "ram_gb"),
    [
        (24576, 64.0),
        (16384, 32.0),
        (12288, 32.0),
        (8192, 16.0),
        (6144, 16.0),
    ],
)
def test_recommended_model_always_passes_its_own_fit_check(vram_mb, ram_gb):
    from aihwbench.analysis.recommend import recommend_configuration

    report = recommend_configuration({"gpu_vram_mb": vram_mb, "ram_gb": ram_gb})
    fit = report["fit_check"]
    assert fit["fits"] is True
    assert fit["fit_target"] == "vram", (
        "a GPU machine's recommendation must fit in VRAM, not spill to RAM"
    )


def test_recommendation_states_the_quantization_it_assumed():
    """The parameter ceiling is meaningless without the density behind it."""
    from aihwbench.analysis.recommend import recommend_configuration

    report = recommend_configuration({"gpu_vram_mb": 8192, "ram_gb": 16.0})
    assert report["assumed_quantization"] == "q4_k_m"
    assert any("bits/weight" in reason for reason in report["reasons"])


def test_recommendation_without_memory_data_proposes_no_size():
    """No budget means no ceiling; inventing one would be a guess."""
    from aihwbench.analysis.recommend import recommend_configuration

    report = recommend_configuration({})
    assert report["recommended_model_parameters_b"] is None


def test_measured_results_upgrade_the_evidence_tier():
    from aihwbench.analysis.recommend import recommend_configuration

    measured = [
        {
            "runtime": {"name": "llama.cpp", "device": "cuda"},
            "metrics": {"generation_tokens_per_second": 120.0},
        }
    ]
    report = recommend_configuration({"gpu_vram_mb": 8192, "ram_gb": 16.0}, measured)
    assert report["evidence_tier"] == "measured"
    assert report["recommended_runtime"] == "llama.cpp"


# --- Energy figures must not outlive the baseline they were measured against -
#
# Regression tests for a discrepancy observed on real hardware: the same
# workload on the same machine produced 0.0777 J/token against a 14.9 W idle
# baseline and 0.0009 J/token against a 31.4 W one. Neither power reading was
# wrong. The second run simply began with a model still resident in VRAM, so
# the card sat at raised clocks and almost all of the measured draw was
# baseline. Presented bare, an 84x swing driven by nothing but what ran
# beforehand reads as a hardware or efficiency difference.


def test_energy_flags_a_figure_that_is_mostly_baseline():
    out = compute_energy_metrics(
        average_power_watts=31.6,
        idle_power_watts=31.41,
        generation_tokens_per_second=206.57,
        requests_per_second=None,
    )
    # The measurement is still reported -- withholding it would hide real data.
    assert out["energy_joules_per_token"] is not None
    assert out["incremental_share_of_gross"] < 0.01
    assert out["incremental_is_robust"] is False
    assert "baseline" in out["caveat"]


def test_energy_does_not_flag_a_workload_dominated_figure():
    out = compute_energy_metrics(
        average_power_watts=120.0,
        idle_power_watts=20.0,
        generation_tokens_per_second=40.0,
        requests_per_second=None,
    )
    assert out["incremental_share_of_gross"] == pytest.approx(0.8333, abs=1e-4)
    assert out["incremental_is_robust"] is True
    assert out["caveat"] is None


def test_energy_robustness_is_unknown_without_a_baseline():
    """No baseline means no claim either way, not a passing grade."""
    out = compute_energy_metrics(
        average_power_watts=120.0,
        idle_power_watts=None,
        generation_tokens_per_second=40.0,
        requests_per_second=None,
    )
    assert out["incremental_is_robust"] is None
    assert out["incremental_share_of_gross"] is None
    assert out["caveat"] is None


def test_the_two_measured_baselines_are_told_apart():
    """The exact pair of readings that motivated this, side by side."""
    resident = compute_energy_metrics(31.6, 31.41, 206.57, None)
    evicted = compute_energy_metrics(31.6, 14.9, 206.57, None)
    assert evicted["energy_joules_per_token"] > resident["energy_joules_per_token"] * 50
    assert evicted["incremental_is_robust"] is True
    assert resident["incremental_is_robust"] is False


def test_energy_below_the_noise_floor_is_not_reported_as_zero():
    """Measured: gross 28.26 W under load against a 29.62 W idle baseline.

    A 0.5B model held an RTX 3080 Ti at ~6% utilization, and the card's idle
    draw drifted by more than the workload added. The old clamp published
    `energy_joules_per_token: 0.0` -- an assertion that generating tokens was
    free. It costs something; this sensor simply cannot resolve how much.
    """
    out = compute_energy_metrics(
        average_power_watts=28.26,
        idle_power_watts=29.62,
        generation_tokens_per_second=206.0,
        requests_per_second=None,
    )
    assert out["incremental_power_watts"] is None
    assert out["energy_joules_per_token"] is None
    assert out["energy_joules_per_1k_tokens"] is None
    assert out["incremental_is_robust"] is None
    assert "below the resolution" in out["caveat"]


def test_energy_equal_power_is_also_unresolved():
    """Exactly equal is no more informative than lower."""
    out = compute_energy_metrics(30.0, 30.0, 100.0, None)
    assert out["incremental_power_watts"] is None
    assert out["energy_joules_per_token"] is None
    assert out["caveat"] is not None


def test_energy_reports_a_resolvable_difference_however_small():
    """The guard must not swallow real, small measurements."""
    out = compute_energy_metrics(30.5, 30.0, 100.0, None)
    assert out["incremental_power_watts"] == pytest.approx(0.5)
    assert out["energy_joules_per_token"] == pytest.approx(0.005)
    # Small and honestly flagged as baseline-dominated, but not withheld.
    assert out["incremental_is_robust"] is False


# --- The headline metric's own stability ------------------------------------


def _run_with_throughput(values: list[float]) -> dict:
    """A result whose iterations produce the given per-iteration tok/s."""
    return {
        "metrics": {},
        "iterations": [
            {"completion_tokens": 100, "eval_seconds": 100.0 / v, "total_latency_ms": 2000.0}
            for v in values
        ],
    }


def test_throughput_decline_is_reported_when_sustained():
    """The measured series that motivated this: 327, 342, 118, 124, 84 tok/s."""
    from aihwbench.quality import per_iteration_throughput, throughput_decline

    values = [327.4, 341.6, 118.0, 123.9, 84.3]
    decline = throughput_decline(values)
    assert decline is not None
    # Halves, not endpoints: (334.5 - 104.1) / 334.5.
    assert decline["decline_fraction"] == pytest.approx(0.689, abs=1e-3)
    assert decline["early_mean_tps"] == pytest.approx(334.5, abs=0.1)
    assert decline["late_mean_tps"] == pytest.approx(104.1, abs=0.1)

    # And the helper recovers the same series from iteration records.
    recovered = per_iteration_throughput(_run_with_throughput(values)["iterations"])
    assert recovered == pytest.approx(values, rel=1e-6)


def test_steady_throughput_is_not_called_a_decline():
    from aihwbench.quality import throughput_decline

    assert throughput_decline([200.0, 198.0, 201.0, 199.0, 200.0]) is None


def test_one_low_iteration_is_not_a_decline():
    """A dip that recovers is noise, and saying otherwise cries wolf."""
    from aihwbench.quality import throughput_decline

    assert throughput_decline([200.0, 90.0, 205.0, 198.0, 202.0]) is None


def test_throughput_decline_needs_enough_iterations():
    """Halves of a 3-point series overlap or omit a point; either way the
    split decides the answer, so no claim is made below four."""
    from aihwbench.quality import throughput_decline

    assert throughput_decline([300.0, 100.0]) is None
    assert throughput_decline([300.0, 100.0, 90.0]) is None


def test_a_high_opening_iteration_is_not_a_collapse():
    """The false positive that endpoint comparison produced.

    333, 180, 266, 258, 242 tok/s recovers after one low iteration. Its first
    and last values differ by 27%; its halves differ by 2%. An endpoint test
    called this a sustained decline and would have put a throttling story on
    an ordinary noisy run.
    """
    from aihwbench.quality import throughput_decline

    assert throughput_decline([332.8, 179.9, 265.9, 258.4, 241.6]) is None


def test_quality_gate_fails_on_unstable_headline_throughput():
    """Latency CV alone let a 56%-CV throughput number through.

    Total latency here is dominated by time-to-first-token, so it barely
    moves while generation throughput swings four-fold -- exactly the shape
    of the run that exposed this.
    """
    from aihwbench.quality import data_quality_report

    result = {
        "metrics": {"generation_tps_cv": 0.5603},
        "iterations": [
            {"completion_tokens": 29, "eval_seconds": s, "total_latency_ms": lat}
            for s, lat in (
                (0.0886, 2114.0),
                (0.0849, 2136.0),
                (0.2458, 2338.0),
                (0.2340, 2321.0),
                (0.3440, 2436.0),
            )
        ],
    }
    checks = data_quality_report(result)["checks"]
    assert checks["cv_latency"] < 0.1  # latency looks fine...
    assert checks["cv_generation_throughput"] > 0.5  # ...throughput does not
    assert checks["variance_acceptable"] is False
    assert checks["sustained_decline"] is not None


def test_quality_gate_accepts_a_stable_run():
    from aihwbench.quality import data_quality_report

    result = {
        "metrics": {},
        "iterations": [
            {"completion_tokens": 100, "eval_seconds": s, "total_latency_ms": 1000.0}
            for s in (0.50, 0.51, 0.49, 0.50, 0.52)
        ],
    }
    checks = data_quality_report(result)["checks"]
    assert checks["variance_acceptable"] is True
    assert checks["sustained_decline"] is None


# --- A difference smaller than the baseline's own wobble is not a measurement -
#
# A card at rest is not at a constant draw. Measured on the reference machine
# within one session: 14.9 W, 29.3 W, 30.3 W and 31.4 W, all honestly sampled
# as "idle" — and with a model resident it oscillated between 14 W and 21 W at
# 0% GPU utilization, a 50% swing a two-second window can land anywhere in.


def test_incremental_inside_the_baseline_spread_is_not_robust():
    out = compute_energy_metrics(
        average_power_watts=20.0,
        idle_power_watts=17.0,  # workload added 3 W
        generation_tokens_per_second=100.0,
        requests_per_second=None,
        idle_power_spread_watts=7.0,  # the baseline itself moved 7 W
    )
    assert out["incremental_is_robust"] is False
    assert "inside the noise of what was subtracted" in out["caveat"]
    # The figure is still reported; only the confidence is withheld.
    assert out["energy_joules_per_token"] is not None


def test_incremental_clear_of_the_spread_stays_robust():
    out = compute_energy_metrics(
        average_power_watts=53.3,
        idle_power_watts=31.2,  # workload added 22 W
        generation_tokens_per_second=280.0,
        requests_per_second=None,
        idle_power_spread_watts=1.5,
    )
    assert out["incremental_is_robust"] is True
    assert out["caveat"] is None


def test_an_unmeasured_spread_does_not_change_the_verdict():
    """Older baselines carry no spread; absence must not imply instability."""
    with_spread = compute_energy_metrics(53.3, 31.2, 280.0, None, idle_power_spread_watts=None)
    assert with_spread["incremental_is_robust"] is True
    assert with_spread["idle_power_spread_watts"] is None


def test_the_spread_is_published_so_a_reader_can_judge():
    out = compute_energy_metrics(53.3, 31.2, 280.0, None, idle_power_spread_watts=2.25)
    assert out["idle_power_spread_watts"] == 2.25


# --- Overlap evaluators: ROUGE-L and SQuAD-style token F1 --------------------
#
# The closest academic competitor reports task quality — MMLU, SQuAD F1,
# ROUGE-L, Spider — where this project had exact match, JSON validity, and
# cosine similarity over vectors the caller supplies. These two are pure
# algorithms: no dataset is bundled, so nothing depends on a licence this
# repository cannot grant.


def _score(name: str, response: str, expected: str | None):
    from aihwbench.evaluators import get_evaluator

    return get_evaluator(name).evaluate(response, expected)


def test_rouge_l_scores_an_exact_reference_at_one():
    assert _score("rouge_l", "the cat sat on the mat", "the cat sat on the mat").score == 1.0


def test_rouge_l_is_order_sensitive_and_token_f1_is_not():
    """The reason both exist.

    Word order distinguishes a summary from a bag of the right words, and is
    irrelevant to a short factual answer. Reversing a sentence halves ROUGE-L
    and leaves token F1 untouched.
    """
    reversed_words = "mat the on sat cat the"
    reference = "the cat sat on the mat"
    assert _score("rouge_l", reversed_words, reference).score == 0.5
    assert _score("token_f1", reversed_words, reference).score == 1.0


def test_no_overlap_scores_zero_not_none():
    """Zero is a measurement here; None would mean "not scored"."""
    assert _score("rouge_l", "completely unrelated words", "the cat sat").score == 0.0
    assert _score("token_f1", "completely unrelated words", "the cat sat").score == 0.0


def test_an_empty_side_is_unscored_rather_than_zero():
    """Precision or recall is undefined, and 0.0 would read as "scored badly"."""
    for name in ("rouge_l", "token_f1"):
        assert _score(name, "", "the cat sat").score is None
        assert _score(name, "the cat sat", "").score is None


def test_no_reference_means_no_score():
    for name in ("rouge_l", "token_f1"):
        result = _score(name, "anything", None)
        assert result.score is None
        assert "supplied" in result.detail


def test_token_f1_counts_repeats_once_each():
    """SQuAD's multiset intersection: saying "Paris" three times earns once."""
    assert _score("token_f1", "paris paris paris", "paris").score == 0.5
    assert _score("token_f1", "paris", "paris").score == 1.0


def test_scores_stay_within_the_declared_range():
    from aihwbench.evaluators import get_evaluator

    pairs = [
        ("the quick brown fox", "the quick brown fox jumps"),
        ("x", "the quick brown fox jumps over"),
        ("a b c d e f g", "g f e d c b a"),
    ]
    for name in ("rouge_l", "token_f1"):
        for response, expected in pairs:
            score = get_evaluator(name).evaluate(response, expected).score
            assert score is not None and 0.0 <= score <= 1.0


def test_case_and_punctuation_do_not_change_the_score():
    assert _score("token_f1", "The Cat, sat!", "the cat sat").score == 1.0
    assert _score("rouge_l", "The Cat, sat!", "the cat sat").score == 1.0


def test_digits_are_kept_because_a_wrong_number_is_a_wrong_answer():
    assert _score("token_f1", "1969", "1969").score == 1.0
    assert _score("token_f1", "1970", "1969").score == 0.0
