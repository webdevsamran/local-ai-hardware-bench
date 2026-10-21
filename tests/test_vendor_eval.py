"""Tests for the vendor evaluation framework and hardware benchmark integrations."""

from __future__ import annotations

import json
from pathlib import Path

from aihwbench.report import render_detailed_report, render_report
from aihwbench.vendor_eval import (
    DEFAULT_CONVERSATIONAL_SLO_TPS,
    ISLOSLPair,
    STANDARD_CONCURRENCY_SWEEP,
    STANDARD_ISL_OSL_GRID,
    STANDARD_POOLING_BATCH_SWEEP,
    STANDARD_POOLING_SEQ_SWEEP,
    VendorEvalPlan,
    VendorModelSpec,
    calculate_gross_efficiency,
    check_per_user_slo,
)


def test_isl_osl_pair() -> None:
    pair = ISLOSLPair(1024, 1024)
    assert pair.input_tokens == 1024
    assert pair.output_tokens == 1024
    assert pair.label == "1024/1024"


def test_standard_grids_and_sweeps() -> None:
    assert len(STANDARD_ISL_OSL_GRID) >= 5
    assert ISLOSLPair(1024, 1024) in STANDARD_ISL_OSL_GRID
    assert 1 in STANDARD_CONCURRENCY_SWEEP
    assert 64 in STANDARD_CONCURRENCY_SWEEP
    assert 256 in STANDARD_CONCURRENCY_SWEEP
    assert 1 in STANDARD_POOLING_BATCH_SWEEP
    assert 256 in STANDARD_POOLING_SEQ_SWEEP


def test_gross_efficiency_calculation() -> None:
    # 2099 tok/s at 142 W -> ~14.78 tok/s/W
    eff = calculate_gross_efficiency(2099.0, 142.0)
    assert eff == 14.78

    # Edge cases
    assert calculate_gross_efficiency(None, 142.0) is None
    assert calculate_gross_efficiency(2099.0, None) is None
    assert calculate_gross_efficiency(2099.0, 0.0) is None
    assert calculate_gross_efficiency(-10.0, 142.0) is None


def test_per_user_slo() -> None:
    assert check_per_user_slo(45.0, 40.0) is True
    assert check_per_user_slo(40.0, 40.0) is True
    assert check_per_user_slo(39.9, 40.0) is False
    assert check_per_user_slo(None) is None


def test_vendor_eval_plan_serialization(tmp_path: Path) -> None:
    spec1 = VendorModelSpec(
        model_id="furiosa-ai/Qwen3-4B-FP8",
        task="generate",
        display_name="Qwen3-4B-FP8",
        notes=["Flagship 4B model"],
        args=["--isl", "1024", "--osl", "1024"],
        concurrency_sweep=[1, 4, 16, 64, 128, 256],
    )
    plan = VendorEvalPlan(
        vendor_name="FuriosaAI",
        hardware_name="RNGD",
        models=[spec1],
        common_args=["--warmup", "1"],
        runner_script="furiosa_llm_runner.py",
        min_free_disk_gb=20.0,
    )

    plan_path = tmp_path / "test_plan.json"
    plan.save_json(plan_path)
    assert plan_path.exists()

    loaded = VendorEvalPlan.load_json(plan_path)
    assert loaded.vendor_name == "FuriosaAI"
    assert loaded.hardware_name == "RNGD"
    assert len(loaded.models) == 1
    assert loaded.models[0].model_id == "furiosa-ai/Qwen3-4B-FP8"
    assert loaded.models[0].concurrency_sweep == [1, 4, 16, 64, 128, 256]


def test_render_detailed_report_with_vendor_eval_matrix() -> None:
    result = {
        "run_id": "rngd-qwen3-4b-01",
        "schema_version": "2.2.0",
        "timestamp": "2026-10-21T02:00:00Z",
        "model": {
            "name": "Qwen3-4B-FP8",
            "id": "furiosa-ai/Qwen3-4B-FP8",
            "parameters": 4000000000,
            "precision": "FP8",
            "tuning_note": "Reference tuned checkpoint",
        },
        "system": {
            "os": "Linux",
            "os_version": "5.15.0",
            "cpu": "AMD EPYC 7713",
            "ram_gb": 1007,
            "npu": {
                "card": "FuriosaAI RNGD",
                "processing_elements": 8,
                "configurable_tdp_watts": "150-200",
                "peak_power_rating_watts": 300,
                "telemetry_tool": "furiosa-smi",
            },
        },
        "runtime": {
            "name": "furiosa-llm",
            "version": "2026.4.0",
            "backend": "npu",
            "flags": "overlap_scheduling=True, prefix_caching=False",
        },
        "workload": {
            "input_tokens": 1024,
            "output_tokens": 1024,
            "measured_runs": 3,
            "warmup_runs": 1,
        },
        "metrics": {
            "ttft_ms": 66.78,
            "prompt_tokens_per_second": 15333.9,
            "generation_tokens_per_second": 143.4,
            "average_power_watts": 88.5,
            "performance_per_watt": 1.62,
        },
        "single_stream_isl_osl_matrix": [
            {
                "input_tokens": 1024,
                "output_tokens": 1024,
                "runs": 3,
                "ttft_mean_ms": 66.78,
                "prompt_tps": 15333.9,
                "decode_tps": 143.4,
                "tpot_mean_ms": 6.97,
                "power_w": 88.5,
                "efficiency_tok_s_per_w": 1.62,
            }
        ],
        "concurrency_sweep": [
            {
                "concurrency": 64,
                "input_tokens": 1024,
                "output_tokens": 1024,
                "aggregate_output_tps": 2047.5,
                "per_user_decode_tps_mean": 32.0,
                "meets_slo": False,
                "ttft_mean_ms": 1150.0,
                "avg_power_w": 144.2,
                "efficiency_tok_s_per_w": 14.2,
            },
            {
                "concurrency": 128,
                "input_tokens": 1024,
                "output_tokens": 1024,
                "aggregate_output_tps": 2447.4,
                "per_user_decode_tps_mean": 19.1,
                "meets_slo": False,
                "ttft_mean_ms": 2300.0,
                "avg_power_w": 152.0,
                "efficiency_tok_s_per_w": 16.1,
            },
        ],
    }

    report_md = render_detailed_report(result)
    assert "# Benchmark Evaluation Report: Qwen3-4B-FP8" in report_md
    assert "8 PEs" in report_md
    assert "TDP 150-200 W" in report_md
    assert "Peak 300 W" in report_md
    assert "furiosa-smi" in report_md
    assert "1024 in / 1024 out" in report_md
    assert "Single-Stream Input/Output Length Matrix (`ISL / OSL` Grid)" in report_md
    assert "Multi-Stream Concurrency Scaling Sweep & Per-User SLO Capacity" in report_md
    assert "$C = 64$" in report_md
    assert "**2,047.50**" in report_md
