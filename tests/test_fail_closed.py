"""Tests for fail-closed dataset/publishing pipelines — Fix 11.

Verifies that publishing/CI paths (strict mode) refuse silent data loss on
unreadable or schema-invalid results, while exploratory local paths remain
tolerant.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from aihwbench.dataset_versioning import build_snapshot_manifest
from aihwbench.export import DatasetLoadError, export_dataset, load_results


def _valid_result(run_id: str = "r1") -> dict:
    return {
        "schema_version": "1.0",
        "run_id": run_id,
        "timestamp": "2026-01-01T00:00:00Z",
        "system": {"os": "linux", "cpu": "CPU", "gpu": None},
        "runtime": {"name": "ollama", "version": "0.5.0", "device": "cpu"},
        "model": {"name": "m", "format": "gguf"},
        "metrics": {"generation_tokens_per_second": 12.5, "ttft_ms": 210.0},
        "reproducibility": {"prompt": "p", "iterations": 3},
    }


def _mk(tmp_path: Path) -> Path:
    published = tmp_path / "published"
    published.mkdir()
    (published / "ok.json").write_text(json.dumps(_valid_result()), encoding="utf-8")
    return published


# ---------------------------------------------------------------------------
# export.load_results / export_dataset strict mode
# ---------------------------------------------------------------------------


def test_load_results_lenient_skips_invalid(tmp_path: Path):
    published = _mk(tmp_path)
    (published / "bad.json").write_text("{ not json", encoding="utf-8")
    results = load_results(published)
    assert [r["run_id"] for r in results] == ["r1"]


def test_load_results_strict_raises_on_corrupt_json(tmp_path: Path):
    published = _mk(tmp_path)
    (published / "bad.json").write_text("{ not json", encoding="utf-8")
    with pytest.raises(DatasetLoadError) as exc:
        load_results(published, strict=True)
    assert "bad.json" in str(exc.value)


def test_load_results_strict_raises_on_schema_invalid(tmp_path: Path):
    published = _mk(tmp_path)
    bad = _valid_result("bad")
    bad["metrics"]["avg_cpu_util_percent"] = 150  # out of range
    (published / "bad.json").write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(DatasetLoadError) as exc:
        load_results(published, strict=True)
    assert "bad.json" in str(exc.value)


def test_snapshot_raises_on_unreadable_member(tmp_path: Path):
    published = _mk(tmp_path)
    (published / "bad.json").write_text("[1,2", encoding="utf-8")
    with pytest.raises(ValueError) as exc:
        build_snapshot_manifest(published, "v1")
    assert "bad.json" in str(exc.value)


def test_snapshot_happy_path_counts_all_members(tmp_path: Path):
    published = _mk(tmp_path)
    manifest = build_snapshot_manifest(published, "v1")
    assert manifest["results_count"] == 1
    assert manifest["members"] == {"ok.json": manifest["members"]["ok.json"]}


# ---------------------------------------------------------------------------
# generate_frontend_data fails closed (strict default)
# ---------------------------------------------------------------------------


def _load_script() -> object:
    spec = importlib.util.spec_from_file_location(
        "gen_frontend",
        Path("scripts/generate_frontend_data.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _write_result(mod: object, tmp_path: Path, data: dict, name: str) -> None:
    dir_ = tmp_path / "published"
    dir_.mkdir(exist_ok=True)
    (dir_ / name).write_text(json.dumps(data), encoding="utf-8")
    mod.RESULTS_DIR = dir_  # type: ignore[attr-defined]
    mod.OUT_DIR = tmp_path / "out"  # type: ignore[attr-defined]
    mod.REPO = tmp_path  # type: ignore[attr-defined]


def test_frontend_data_strict_raises_on_corrupt(tmp_path: Path):
    mod = _load_script()
    _write_result(mod, tmp_path, _valid_result(), "ok.json")
    (tmp_path / "published" / "broken.json").write_text("{ nope", encoding="utf-8")
    with pytest.raises(ValueError) as exc:
        mod._load_results(strict=True)  # type: ignore[attr-defined]
    assert "broken.json" in str(exc.value)


def test_frontend_data_lenient_warns_and_skips(tmp_path: Path, capsys):
    mod = _load_script()
    _write_result(mod, tmp_path, _valid_result(), "ok.json")
    (tmp_path / "published" / "broken.json").write_text("{ nope", encoding="utf-8")
    results = mod._load_results(strict=False)  # type: ignore[attr-defined]
    assert [r["run_id"] for r in results] == ["r1"]
    captured = capsys.readouterr()
    assert "WARN" in captured.err


def test_frontend_data_main_returns_2_on_corrupt(tmp_path: Path):
    mod = _load_script()
    _write_result(mod, tmp_path, _valid_result(), "ok.json")
    (tmp_path / "published" / "broken.json").write_text("{ nope", encoding="utf-8")
    code = mod.main([])  # type: ignore[attr-defined]
    assert code == 2


def test_frontend_data_main_succeeds_on_valid(tmp_path: Path):
    mod = _load_script()
    _write_result(mod, tmp_path, _valid_result(), "ok.json")
    code = mod.main([])  # type: ignore[attr-defined]
    assert code == 0
    assert (tmp_path / "out" / "results.json").exists()


def test_export_dataset_lenient_default_ignores_bad(tmp_path: Path):
    published = _mk(tmp_path)
    (published / "bad.json").write_text("{ broken", encoding="utf-8")
    out = tmp_path / "dataset"
    export_dataset(published, out)
    index = json.loads((out / "index.json").read_text(encoding="utf-8"))
    assert index["count"] == 1


def test_export_dataset_strict_fails_closed(tmp_path: Path):
    published = _mk(tmp_path)
    (published / "bad.json").write_text("{ broken", encoding="utf-8")
    with pytest.raises(DatasetLoadError):
        export_dataset(published, tmp_path / "dataset", strict=True)
