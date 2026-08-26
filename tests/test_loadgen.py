"""Tests for the load generator, sweep engine, manifests, and capacity."""

from __future__ import annotations

import json
import time

import pytest

from aihwbench.capacity import CapacityConfig, run_capacity_ladder
from aihwbench.loadgen import LoadgenConfig, generate_arrivals, run_load
from aihwbench.manifests import ExperimentError, load_experiment
from aihwbench.stats import MIN_SAMPLES_FOR_CI, bootstrap_ci, summarize
from aihwbench.sweep import SweepSpec, best_by, matrix_to_csv_rows, pareto_frontier, run_sweep


def _fast_execute(request_id: int) -> dict:
    time.sleep(0.001)
    return {"completion_tokens": 10, "ttft_ms": 1.0 + request_id * 0.01}


# ---------------------------------------------------------------------------
# Load generator
# ---------------------------------------------------------------------------


def test_loadgen_config_validation():
    with pytest.raises(ValueError):
        LoadgenConfig(pattern="unknown", requests=1)
    with pytest.raises(ValueError):
        LoadgenConfig(concurrency=0, requests=1)
    with pytest.raises(ValueError):
        LoadgenConfig(rate_per_second=0, requests=1)
    with pytest.raises(ValueError):
        LoadgenConfig()  # no requests/duration


def test_arrivals_constant_rate_deterministic():
    cfg = LoadgenConfig(pattern="constant_rate", rate_per_second=100.0, requests=50)
    a = list(generate_arrivals(cfg))
    b = list(generate_arrivals(cfg))
    assert a == b
    assert len(a) == 50
    assert abs((a[-1] - a[0]) - 49 / 100.0) < 1e-9


def test_arrivals_poisson_seeded():
    cfg = LoadgenConfig(pattern="poisson", rate_per_second=50.0, requests=30)
    assert list(generate_arrivals(cfg)) == list(generate_arrivals(cfg))


def test_closed_loop_runs_all_requests():
    records = run_load(LoadgenConfig(requests=12, concurrency=3), _fast_execute)
    assert len(records) == 12
    assert all(r.success for r in records)
    ids = sorted(r.request_id for r in records)
    assert ids == list(range(12))


def test_open_pattern_constant_rate():
    records = run_load(
        LoadgenConfig(pattern="constant_rate", rate_per_second=200.0, requests=8, concurrency=2),
        _fast_execute,
    )
    assert len(records) == 8
    assert all(r.success for r in records)


def test_execute_exception_recorded_as_failure():
    def failing(_rid: int) -> dict:
        raise RuntimeError("boom")

    records = run_load(LoadgenConfig(requests=4), failing)
    assert len(records) == 4
    assert all(not r.success for r in records)
    assert "boom" in records[0].result["error"]


def test_queue_latency_zero_for_closed_loop():
    records = run_load(LoadgenConfig(requests=5), _fast_execute)
    assert all(r.queue_latency_ms >= 0.0 for r in records)


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------


def test_summarize_full_percentile_ladder():
    values = [float(i) for i in range(1, 101)]
    s = summarize(values)
    assert s["count"] == 100
    assert s["min"] == 1.0 and s["max"] == 100.0
    assert s["p50"] == pytest.approx(50.5, abs=1.0)
    assert s["p95"] is not None and s["p99"] is not None and s["p99_9"] is not None
    assert s["stddev"] > 0
    assert s["cv"] is not None and s["cv"] > 0


def test_bootstrap_ci_refuses_small_samples():
    values = [1.0, 2.0, 3.0]
    assert bootstrap_ci(values) is None
    assert bootstrap_ci(values, min_samples=3) is not None


def test_bootstrap_ci_brackets_mean_for_large_samples():
    import random as _random

    rng = _random.Random(7)
    values = [rng.gauss(100.0, 5.0) for _ in range(MIN_SAMPLES_FOR_CI * 5)]
    ci = bootstrap_ci(values)
    assert ci is not None
    lo, hi = ci
    mean = sum(values) / len(values)
    assert lo <= mean <= hi


def test_summarize_empty_is_all_none_not_zero():
    s = summarize([])
    assert s["count"] == 0
    assert s["mean"] is None and s["p95"] is None


# ---------------------------------------------------------------------------
# Sweep engine
# ---------------------------------------------------------------------------


def test_sweep_combinations_cartesian_product():
    spec = SweepSpec(axes={"a": (1, 2), "b": ("x", "y")}, base={"fixed": True})
    combos = spec.combinations()
    assert len(combos) == 4
    assert {"a": 1, "b": "x", "fixed": True} in combos


def test_run_sweep_records_failures_without_aborting():
    def run_fn(point: dict) -> dict:
        if point["v"] == 2:
            raise RuntimeError("point failed")
        return {"run_id": f"r{point['v']}", "metrics": {"generation_tokens_per_second": point["v"]}}

    spec = SweepSpec(axes={"v": (1, 2, 3)})
    matrix = run_sweep(spec, run_fn)
    assert len(matrix) == 3
    assert matrix[1]["error"] == "point failed"
    assert matrix[0]["metrics"]["generation_tokens_per_second"] == 1


def test_pareto_frontier_and_best_by():
    def run_fn(point: dict) -> dict:
        speed = {1: 10.0, 2: 20.0, 3: 15.0}[point["v"]]
        mem = {1: 100.0, 2: 400.0, 3: 200.0}[point["v"]]
        return {
            "run_id": str(point["v"]),
            "metrics": {"generation_tokens_per_second": speed, "peak_vram_mb": mem},
        }

    matrix = run_sweep(SweepSpec(axes={"v": (1, 2, 3)}), run_fn)
    front = pareto_frontier(matrix, {"generation_tokens_per_second": True, "peak_vram_mb": False})
    front_ids = {r["run_id"] for r in front}
    # Point 2 dominates nothing on memory; points 1 and 3 are trade-offs.
    assert "1" in front_ids and "3" in front_ids
    assert best_by(matrix, "generation_tokens_per_second")["run_id"] == "2"
    rows = matrix_to_csv_rows(matrix)
    assert rows[0]["param_v"] == 1


# ---------------------------------------------------------------------------
# Manifests
# ---------------------------------------------------------------------------


def test_manifest_json_round_trip(tmp_path):
    path = tmp_path / "exp.json"
    path.write_text(
        json.dumps(
            {
                "name": "test-exp",
                "runtimes": ["ollama"],
                "models": ["llama3.2:1b"],
                "repetitions": 2,
                "sweep": {"max_tokens": [32, 64]},
            }
        ),
        encoding="utf-8",
    )
    exp = load_experiment(path)
    assert exp.name == "test-exp"
    assert exp.repetitions == 2
    assert exp.sweep == {"max_tokens": (32, 64)}
    assert exp.devices == ("auto",)


def test_manifest_rejects_unknown_keys(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"name": "x", "bogus_key": 1}), encoding="utf-8")
    with pytest.raises(ExperimentError):
        load_experiment(path)


def test_manifest_requires_name(tmp_path):
    path = tmp_path / "noname.json"
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(ExperimentError):
        load_experiment(path)


def test_manifest_unsupported_format(tmp_path):
    path = tmp_path / "exp.xml"
    path.write_text("<x/>", encoding="utf-8")
    with pytest.raises(ExperimentError):
        load_experiment(path)


# ---------------------------------------------------------------------------
# Capacity
# ---------------------------------------------------------------------------


def test_capacity_ladder_identifies_sustainable_concurrency():
    def execute(_rid: int) -> dict:
        time.sleep(0.002)
        return {"completion_tokens": 20, "ttft_ms": 5.0}

    report = run_capacity_ladder(
        CapacityConfig(concurrency_levels=(1, 2, 4), requests_per_level=6), execute
    )
    data = report.as_dict()
    assert len(data["levels"]) == 3
    assert all(lv["errors"] == 0 for lv in data["levels"])
    assert data["sustainable_concurrency"] in (1, 2, 4)
    assert "p95" in data["rule"]
    # Throughput should be measured at every level.
    assert all(lv["requests_per_second"] and lv["requests_per_second"] > 0 for lv in data["levels"])


def test_capacity_config_validation():
    with pytest.raises(ValueError):
        CapacityConfig(concurrency_levels=())
    with pytest.raises(ValueError):
        CapacityConfig(requests_per_level=0)
