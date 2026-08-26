"""Tests for the typed domain model (benchmark.domain)."""

from __future__ import annotations

import json
import pathlib

import pytest

from aihwbench.domain import BenchmarkResult, MetricSet, SystemInfo


def _published_results() -> list[dict]:
    results = []
    for path in sorted(pathlib.Path("results/published").glob("*.json")):
        results.append(json.loads(path.read_text(encoding="utf-8")))
    return results


def test_parses_published_schema_1_results():
    """Every committed published result must parse into the typed model."""
    docs = _published_results()
    assert docs, "expected published results to exist"
    for doc in docs:
        result = BenchmarkResult.from_dict(doc)
        assert result.run_id == doc["run_id"]
        assert result.system.cpu is not None or result.system.gpu is not None
        # LLM results report generation tok/s; ONNX-style results report
        # inferences/s. At least one throughput metric must be measured.
        assert (
            result.metrics.generation_tokens_per_second is not None
            or result.metrics.throughput_inferences_per_second is not None
        )


def test_round_trip_preserves_measured_values():
    doc = _published_results()[0]
    parsed = BenchmarkResult.from_dict(doc)
    out = parsed.as_dict()
    assert (
        out["metrics"]["generation_tokens_per_second"]
        == (doc["metrics"]["generation_tokens_per_second"])
    )
    assert out["metrics"]["ttft_ms"] == doc["metrics"]["ttft_ms"]


def test_missing_metrics_stay_none():
    metrics = MetricSet.from_dict({})
    assert metrics.ttft_ms is None
    assert metrics.tpot_ms is None  # schema 2.0 field absent in 1.0 docs
    assert metrics.ci95_latency_ms is None


def test_bools_are_rejected_as_numbers():
    metrics = MetricSet.from_dict({"ttft_ms": True})
    assert metrics.ttft_ms is None


def test_system_info_topology_and_gpus():
    system = SystemInfo.from_dict(
        {
            "cpu": "Test CPU",
            "gpus": [
                {
                    "vendor": "NVIDIA",
                    "name": "RTX 3080 Ti",
                    "vram_mb": 16384,
                    "pcie_gen": 4,
                    "pcie_width": 16,
                    "index": 0,
                }
            ],
            "topology": {"numa_nodes": 1, "sockets": 1, "gpu_count": 1},
        }
    )
    assert len(system.gpus) == 1
    assert system.gpus[0].pcie_gen == 4
    assert system.topology.numa_nodes == 1
    assert system.topology.gpu_count == 1


def test_from_dict_rejects_non_object():
    with pytest.raises(TypeError):
        BenchmarkResult.from_dict([1, 2, 3])  # type: ignore[arg-type]
