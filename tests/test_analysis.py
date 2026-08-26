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
from aihwbench.analysis.tune import run_tuner
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
