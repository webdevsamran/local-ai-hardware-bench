"""Tests for the ecosystem modules: comparability, sanitize, fingerprint,
trust, suites, export, exit codes, and plugin discovery."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aihwbench.comparability import (
    CONDITIONALLY_COMPARABLE,
    NOT_COMPARABLE,
    STRICTLY_COMPARABLE,
    compare_classification,
)
from aihwbench.exit_codes import (
    EXIT_NOT_COMPARABLE,
    EXIT_OK,
    EXIT_USAGE_ERROR,
    EXIT_VALIDATION_ERROR,
)
from aihwbench.export import export_dataset
from aihwbench.fingerprint import find_duplicates, result_fingerprint
from aihwbench.sanitize import scan_object
from aihwbench.suites import list_suites, load_suite
from aihwbench.trust import COMMUNITY_VALIDATED, UNVERIFIED, VERIFIED, trust_state


def _result(run_id: str, gen_tps: float) -> dict:
    return {
        "schema_version": "1.0",
        "run_id": run_id,
        "timestamp": "2026-08-22T09:00:00Z",
        "system": {
            "os": "Windows 11",
            "os_version": "10.0.26200",
            "cpu": "Intel i9-12900H",
            "cpu_cores_physical": 14,
            "cpu_cores_logical": 20,
            "gpu": "NVIDIA RTX 3080 Ti Laptop",
            "gpu_vram_mb": 16384,
            "npu": None,
            "ram_gb": 31.7,
            "platform_name": "Predator PT516-52s",
        },
        "runtime": {
            "name": "ollama",
            "version": "0.32.15",
            "backend": "ollama-http-api",
            "device": "auto",
        },
        "model": {
            "name": "qwen2.5:0.5b-instruct-q4_K_M",
            "format": "gguf",
            "quantization": None,
            "parameters": None,
            "checksum": "a8b0c51577010a279d933d14c2a8ab4b268079d44c5c8830c0a93900f1827c67",
        },
        "metrics": {
            "ttft_ms": 45.2,
            "generation_tokens_per_second": gen_tps,
            "total_latency_ms": 2417.27,
            "p50_latency_ms": 2471.55,
            "p95_latency_ms": 2565.49,
        },
        "reproducibility": {
            "prompt": "Explain what a token is in large language models, in two sentences.",
            "max_tokens": 128,
            "temperature": 0.0,
            "seed": 42,
            "context_length": 2048,
            "warmup_runs": 2,
            "iterations": 5,
            "command": "aihwbench benchmark --runtime ollama --model qwen2.5:0.5b",
        },
    }


# --- Comparability -------------------------------------------------------


def test_identical_results_strictly_comparable():
    a = _result("a", 100.0)
    b = _result("b", 110.0)
    assert compare_classification(a, b)["classification"] == STRICTLY_COMPARABLE


def test_different_runtime_not_comparable():
    a = _result("a", 100.0)
    b = _result("b", 110.0)
    b["runtime"]["name"] = "llama.cpp"
    b["runtime"]["backend"] = "llama-server"
    result = compare_classification(a, b)
    assert result["classification"] == NOT_COMPARABLE
    assert "runtime.name" in result["machine_reasons"]


def test_different_model_not_comparable():
    a = _result("a", 100.0)
    b = _result("b", 110.0)
    b["model"]["name"] = "other-model"
    result = compare_classification(a, b)
    assert result["classification"] == NOT_COMPARABLE


def test_different_checksum_not_comparable():
    a = _result("a", 100.0)
    b = _result("b", 110.0)
    b["model"]["checksum"] = "deadbeef"
    result = compare_classification(a, b)
    assert result["classification"] == NOT_COMPARABLE
    assert "model.checksum" in result["machine_reasons"]


def test_different_prompt_not_comparable():
    a = _result("a", 100.0)
    b = _result("b", 110.0)
    b["reproducibility"]["prompt"] = "different prompt"
    assert compare_classification(a, b)["classification"] == NOT_COMPARABLE


def test_different_seed_not_comparable():
    a = _result("a", 100.0)
    b = _result("b", 110.0)
    b["reproducibility"]["seed"] = 7
    assert compare_classification(a, b)["classification"] == NOT_COMPARABLE


def test_power_profile_difference_is_conditional():
    a = _result("a", 100.0)
    b = _result("b", 110.0)
    a["reproducibility"]["power_profile"] = "Balanced"
    b["reproducibility"]["power_profile"] = "High performance"
    result = compare_classification(a, b)
    assert result["classification"] == CONDITIONALLY_COMPARABLE


def test_machine_reasons_are_stable_keys():
    a = _result("a", 100.0)
    b = _result("b", 110.0)
    b["runtime"]["name"] = "llama.cpp"
    reasons = compare_classification(a, b)["machine_reasons"]
    assert all(isinstance(r, str) and "." in r for r in reasons)


# --- Privacy sanitization ------------------------------------------------


def test_clean_result_passes_scan():
    clean, findings = scan_object(_result("a", 100.0))
    assert clean
    assert findings == []


def test_mac_address_detected():
    clean, findings = scan_object({"note": "mac 00:1A:2B:3C:4D:5E"})
    assert not clean
    assert any("MAC" in f for f in findings)


def test_ipv4_detected():
    clean, findings = scan_object({"endpoint": "http://203.0.113.42/api"})
    assert not clean
    assert any("IPv4" in f for f in findings)


def test_github_token_detected():
    token = "ghp_" + "a" * 36
    clean, findings = scan_object({"token": token})
    assert not clean
    assert any("token" in f.lower() for f in findings)


def test_windows_home_path_detected():
    clean, findings = scan_object({"path": "C:\\\\Users\\\\alice\\\\models"})
    assert not clean
    assert any("home" in f.lower() for f in findings)


def test_serial_number_detected():
    clean, findings = scan_object({"serial number": "SN123456789"})
    assert not clean
    assert any("serial" in f.lower() for f in findings)


# --- Fingerprints --------------------------------------------------------


def test_fingerprint_deterministic():
    a = _result("a", 100.0)
    b = _result("b", 110.0)
    assert result_fingerprint(a) == result_fingerprint(b)


def test_fingerprint_changes_with_model():
    a = _result("a", 100.0)
    b = _result("b", 100.0)
    b["model"]["name"] = "other"
    assert result_fingerprint(a) != result_fingerprint(b)


def test_find_duplicates_groups_same_experiment():
    a = _result("run-1", 100.0)
    b = _result("run-2", 110.0)
    c = _result("run-3", 120.0)
    c["model"]["name"] = "different-model"
    groups = find_duplicates([a, b, c])
    assert len(groups) == 1
    assert set(groups[0]) == {"run-1", "run-2"}


# --- Trust states --------------------------------------------------------


def test_trust_state_normalization():
    assert trust_state(VERIFIED) == VERIFIED
    assert trust_state(COMMUNITY_VALIDATED) == COMMUNITY_VALIDATED
    assert trust_state(None) == UNVERIFIED
    assert trust_state("bogus") == UNVERIFIED


# --- Suites --------------------------------------------------------------


def test_list_suites_contains_expected_profiles():
    suites = list_suites()
    for expected in ("smoke", "standard", "latency", "throughput", "efficiency", "sustained"):
        assert expected in suites


def test_load_suite_smoke():
    suite = load_suite("smoke")
    assert suite["name"] == "smoke"
    workload = suite["workload"]
    assert workload["temperature"] == 0.0
    assert workload["seed"] == 42
    assert workload["max_tokens"] > 0


def test_load_suite_missing_raises():
    with pytest.raises(FileNotFoundError):
        load_suite("does-not-exist")


# --- Exporters -----------------------------------------------------------


def test_export_dataset_generates_views(tmp_path: Path):
    published = tmp_path / "published"
    published.mkdir()
    (published / "run-1.json").write_text(json.dumps(_result("run-1", 100.0)), encoding="utf-8")
    outputs = export_dataset(published, tmp_path / "dataset")
    names = {p.name for p in outputs}
    assert names == {"index.json", "dataset.csv", "LEADERBOARD.md"}
    index = json.loads((tmp_path / "dataset" / "index.json").read_text(encoding="utf-8"))
    assert index["count"] == 1
    assert index["results"][0]["run_id"] == "run-1"
    csv_text = (tmp_path / "dataset" / "dataset.csv").read_text(encoding="utf-8")
    assert "run_id" in csv_text and "run-1" in csv_text
    md_text = (tmp_path / "dataset" / "LEADERBOARD.md").read_text(encoding="utf-8")
    assert "run-1" in md_text


def test_export_skips_invalid_results(tmp_path: Path):
    published = tmp_path / "published"
    published.mkdir()
    bad = _result("bad", 100.0)
    bad["metrics"]["avg_cpu_util_percent"] = 150  # out of range
    (published / "bad.json").write_text(json.dumps(bad), encoding="utf-8")
    outputs = export_dataset(published, tmp_path / "dataset")
    index = json.loads((tmp_path / "dataset" / "index.json").read_text(encoding="utf-8"))
    assert index["count"] == 0
    assert len(outputs) == 3


# --- Exit codes ----------------------------------------------------------


def test_exit_code_values_are_stable():
    assert EXIT_OK == 0
    assert EXIT_VALIDATION_ERROR == 1
    assert EXIT_USAGE_ERROR == 2
    assert EXIT_NOT_COMPARABLE == 3
