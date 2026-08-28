"""Fail-closed bundle verification tests (Phase A security hardening).

Regression coverage for the audit finding: verify_bundle used to report
extra unmanifested ZIP members but still return ``valid=true``, so an
injected unchecksummed member could be accepted. Extra members are now
rejected by default; manifest grammar, duplicate members, unsafe names
and archive safety caps are enforced.
"""

from __future__ import annotations

import json
import zipfile

import pytest

from aihwbench import bundles as bundles_mod
from aihwbench.bundles import create_bundle, verify_bundle


def _result(run_id: str = "run-1") -> dict:
    return {
        "schema_version": "1.0",
        "run_id": run_id,
        "timestamp": "2026-01-01T00:00:00Z",
        "runtime": {"name": "ollama", "version": "0.5.0"},
        "model": {"name": "m", "format": "gguf"},
        "metrics": {"generation_tokens_per_second": 10.0},
    }


def _rewrite(path, names, mutate=None):
    """Rewrite a zip with the given member names, applying an optional
    mutation that may add or replace members (name -> bytes)."""
    with zipfile.ZipFile(path) as zf:
        contents = {n: zf.read(n) for n in zf.namelist()}
    if mutate:
        contents = mutate(contents)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for n, data in contents.items():
            zf.writestr(n, data)


def test_roundtrip_bundle_is_valid(tmp_path):
    path = create_bundle(tmp_path / "run.aihwbench", _result())
    report = verify_bundle(path)
    assert report["valid"] is True
    assert report["policy"] == "strict"
    assert report["violations"] == []
    assert report["manifest_errors"] == []


def test_injected_unmanifested_member_is_rejected(tmp_path):
    """P0 regression: an unchecksummed injected member must invalidate."""
    path = create_bundle(tmp_path / "run.aihwbench", _result())
    _rewrite(
        path,
        None,
        mutate=lambda c: {**c, "injected.json": b'{"evil": true}'},
    )
    report = verify_bundle(path)
    assert report["valid"] is False
    assert report["extra_members"] == ["injected.json"]
    assert report["policy"] == "extra members rejected"


def test_extra_members_opt_in_reports_but_tolerates(tmp_path):
    path = create_bundle(tmp_path / "run.aihwbench", _result())
    _rewrite(path, None, mutate=lambda c: {**c, "extra.txt": b"hello"})
    report = verify_bundle(path, allow_extra_members=True)
    assert report["valid"] is True
    assert report["extra_members"] == ["extra.txt"]
    assert "tolerated" in report["policy"]


def test_duplicate_manifest_entry_invalidates(tmp_path):
    path = create_bundle(tmp_path / "run.aihwbench", _result())
    _rewrite(
        path,
        None,
        mutate=lambda c: {
            **c,
            "MANIFEST.sha256": c["MANIFEST.sha256"] + c["MANIFEST.sha256"].splitlines()[0] + b"\n",
        },
    )
    report = verify_bundle(path)
    assert report["valid"] is False
    assert any("duplicate" in e for e in report["manifest_errors"])


def test_malformed_manifest_digest_invalidates(tmp_path):
    path = create_bundle(tmp_path / "run.aihwbench", _result())
    _rewrite(
        path,
        None,
        mutate=lambda c: {
            **c,
            "MANIFEST.sha256": b"deadbeef  result.json\n",
        },
    )
    report = verify_bundle(path)
    assert report["valid"] is False
    assert report["manifest_errors"]


def test_traversal_member_name_invalidates(tmp_path):
    path = create_bundle(tmp_path / "run.aihwbench", _result())
    _rewrite(
        path,
        None,
        mutate=lambda c: {**c, "../evil.json": b"x"},
    )
    report = verify_bundle(path)
    assert report["valid"] is False
    assert any("unsafe member name" in v for v in report["violations"])


def test_member_count_cap(monkeypatch, tmp_path):
    monkeypatch.setattr(bundles_mod, "MAX_MEMBER_COUNT", 2)
    path = create_bundle(
        tmp_path / "run.aihwbench",
        _result(),
        environment={"os": "linux"},
        workload={"id": "w"},
        telemetry={"samples": 1},
    )
    report = verify_bundle(path)
    assert report["valid"] is False
    assert any("member count" in v for v in report["violations"])


def test_compression_ratio_cap(monkeypatch, tmp_path):
    monkeypatch.setattr(bundles_mod, "MAX_COMPRESSION_RATIO", 10.0)
    result = _result()
    result["metrics"]["padding"] = "0" * 20000  # highly compressible
    path = create_bundle(tmp_path / "run.aihwbench", result)
    report = verify_bundle(path)
    assert report["valid"] is False
    assert any("compression ratio" in v for v in report["violations"])


def test_uncompressed_size_cap(monkeypatch, tmp_path):
    monkeypatch.setattr(bundles_mod, "MAX_UNCOMPRESSED_BYTES", 64)
    path = create_bundle(tmp_path / "run.aihwbench", _result())
    report = verify_bundle(path)
    assert report["valid"] is False
    assert any("uncompressed size" in v for v in report["violations"])


def test_duplicate_member_names_invalidates(tmp_path):
    path = create_bundle(tmp_path / "run.aihwbench", _result())
    with zipfile.ZipFile(path) as zf:
        contents = {n: zf.read(n) for n in zf.namelist()}
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for n, data in contents.items():
            zf.writestr(n, data)
        with pytest.warns(UserWarning, match="Duplicate name"):
            zf.writestr("result.json", json.dumps(_result("dup")).encode("utf-8"))
    report = verify_bundle(path)
    assert report["valid"] is False
    assert any("duplicate member names" in v for v in report["violations"])


def test_missing_bundle_file_reports_reason(tmp_path):
    report = verify_bundle(tmp_path / "does-not-exist.aihwbench")
    assert report["valid"] is False
    assert report["reason"] == "bundle not found"
