"""Tests for provenance, bundles, reproducibility, quality, dataset versioning."""

from __future__ import annotations

import json
import zipfile

import pytest

from aihwbench.bundles import create_bundle, verify_bundle
from aihwbench.dataset_versioning import build_snapshot_manifest, diff_snapshots
from aihwbench.provenance import (
    canonical_json,
    compute_provenance,
    sha256_canonical,
    verify_hashes,
)
from aihwbench.quality import data_quality_report, flag_anomalies, invalidate_result
from aihwbench.repro import check_reproduction, env_diff, reproducibility_score


def _result(run_id: str = "run-1", **overrides) -> dict:
    base = {
        "schema_version": "1.0",
        "run_id": run_id,
        "timestamp_utc": "2026-01-01T00:00:00Z",
        "runtime": {"name": "ollama", "version": "0.5.0", "device": "cpu"},
        "model": {"name": "test-model", "format": "gguf", "quantization": "Q4_K_M"},
        "metrics": {"generation_tokens_per_second": 10.0},
        "iterations": [{"total_latency_ms": 100.0}, {"total_latency_ms": 110.0}],
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Provenance hashing
# ---------------------------------------------------------------------------


def test_canonical_hash_is_deterministic_and_key_order_insensitive():
    a = {"b": 1, "a": [1, 2]}
    b = {"a": [1, 2], "b": 1}
    assert sha256_canonical(a) == sha256_canonical(b)
    assert canonical_json(a) == '{"a":[1,2],"b":1}'


def test_compute_provenance_excludes_itself():
    result = _result()
    prov = compute_provenance(result, environment={"os": "linux"})
    assert prov["hash_algorithm"] == "sha256"
    assert prov["environment_hash"] is not None
    # Hash of the doc without provenance must match verification.
    with_prov = dict(result, provenance=prov)
    checks = verify_hashes(with_prov)
    assert checks["checks"]["result_hash"] is True


def test_verify_hashes_detects_tampering():
    result = _result()
    prov = compute_provenance(result)
    tampered = dict(result, metrics={"generation_tokens_per_second": 999.0}, provenance=prov)
    checks = verify_hashes(tampered)
    assert checks["checks"]["result_hash"] is False


def test_cosign_interfaces_report_unavailable(monkeypatch):
    from aihwbench import provenance

    monkeypatch.setattr(provenance.shutil, "which", lambda name: None)
    out = provenance.sign_bundle_cosign(__import__("pathlib").Path("x"))
    assert out["signed"] is False and "not installed" in out["reason"]


# ---------------------------------------------------------------------------
# Bundles
# ---------------------------------------------------------------------------


def test_bundle_roundtrip_and_verification(tmp_path):
    result = _result()
    env = {"os": "windows"}
    path = create_bundle(tmp_path / "run.aihwbench", result, environment=env)
    report = verify_bundle(path)
    assert report["valid"] is True
    assert report["members_checked"] == 2


def test_bundle_detects_tampered_member(tmp_path):
    path = create_bundle(tmp_path / "run.aihwbench", _result())
    # Rewrite one member without updating the manifest.
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        contents = {n: zf.read(n) for n in names}
    contents["result.json"] = json.dumps(_result("tampered")).encode("utf-8")
    with zipfile.ZipFile(path, "w") as zf:
        for n, data in contents.items():
            zf.writestr(n, data)
    report = verify_bundle(path)
    assert report["valid"] is False
    assert "result.json" in report["mismatches"]


def test_bundle_missing_file_reports_invalid(tmp_path):
    assert verify_bundle(tmp_path / "nope.aihwbench")["valid"] is False


# ---------------------------------------------------------------------------
# Reproducibility
# ---------------------------------------------------------------------------


def test_env_diff_reports_matching_and_differing():
    a = _result(
        runtime={"name": "ollama", "version": "0.5.0", "device": "cpu"},
        model={"name": "m", "format": "gguf", "quantization": "Q4_K_M"},
    )
    b = _result(
        runtime={"name": "llama.cpp", "version": "0.5.0", "device": "cpu"},
        model={"name": "m", "format": "gguf", "quantization": "Q4_K_M"},
    )
    diff = env_diff(a, b)
    assert diff["matching"]["runtime.version"] == "0.5.0"
    assert diff["differing"]["runtime.name"]["a"] == "ollama"
    assert diff["differing"]["runtime.name"]["b"] == "llama.cpp"


def test_reproducibility_score_counts_present_metadata():
    bare = reproducibility_score(_result())
    rich = reproducibility_score(
        _result(
            git_commit="abc123",
            workload={"id": "chat-short"},
            provenance={"result_hash": "x"},
            model={"checksum": "sha256:abc", "tokenizer": "tok"},
            reproducibility={
                "seed": 42,
                "power_profile": "balanced",
                "command": "aihwbench ...",
                "python_version": "3.12",
            },
        )
    )
    assert bare["score"] < rich["score"]
    assert rich["present"] == rich["total"]
    assert "scientifically valid" in rich["note"]


def test_check_reproduction_lists_blockers():
    out = check_reproduction(_result(), current_system={"os": "linux"})
    assert out["can_attempt"] is False
    assert any("checksum" in b for b in out["blockers"])
    assert isinstance(out["environment_deviations"], list)


# ---------------------------------------------------------------------------
# Data quality / invalidation / anomalies
# ---------------------------------------------------------------------------


def test_data_quality_report_flags_privacy_leak():
    leaky = _result(
        extra={"log": "user dir C:" + chr(92) + "Users" + chr(92) + "samra" + chr(92) + "models"}
    )
    report = data_quality_report(leaky)
    assert report["checks"]["privacy_clean"] is False
    assert "windows_path" in report["checks"]["privacy_hits"]


def test_data_quality_report_clean_result_passes():
    report = data_quality_report(_result())
    assert report["checks"]["privacy_clean"] is True
    assert report["checks"]["trust_state"] == "unreviewed"


def test_invalidate_requires_reason_and_preserves_original():
    original = _result()
    record = invalidate_result(original, "wrong clock source", replacement_run_id="run-2")
    assert record["invalidated_run_id"] == "run-1"
    assert record["replacement_run_id"] == "run-2"
    assert record["original_result"] == original
    with pytest.raises(ValueError):
        invalidate_result(original, "   ")


def test_flag_anomalies_needs_minimum_sample():
    assert flag_anomalies([_result("a"), _result("b")]) == []


def test_flag_anomalies_detects_outlier_without_fraud_verdict():
    # 15 baseline points: max achievable |z| is (n-1)/sqrt(n) ~ 3.6 > 3.
    results = [_result(f"r{i}", metrics={"generation_tokens_per_second": 10.0}) for i in range(15)]
    results.append(_result("outlier", metrics={"generation_tokens_per_second": 500.0}))
    flags = flag_anomalies(results)
    assert len(flags) == 1
    assert flags[0]["run_id"] == "outlier"
    assert flags[0]["action"] == "manual_review"


# ---------------------------------------------------------------------------
# Dataset versioning
# ---------------------------------------------------------------------------


def test_snapshot_manifest_hashes_members_and_diffs(tmp_path):
    (tmp_path / "a.json").write_text(json.dumps(_result("a")), encoding="utf-8")
    (tmp_path / "b.json").write_text(json.dumps(_result("b")), encoding="utf-8")
    snap1 = build_snapshot_manifest(tmp_path, "v1")
    assert snap1["results_count"] == 2
    assert set(snap1["members"]) == {"a.json", "b.json"}
    assert snap1["changes_vs_previous"] is None

    (tmp_path / "c.json").write_text(json.dumps(_result("c")), encoding="utf-8")
    snap2 = build_snapshot_manifest(tmp_path, "v2", previous_manifest=snap1)
    changes = snap2["changes_vs_previous"]
    assert changes["added"] == ["c.json"]
    assert changes["removed"] == []
    assert changes["changed"] == []

    old_new = diff_snapshots(snap1, snap2)
    assert old_new["added"] == ["c.json"]
