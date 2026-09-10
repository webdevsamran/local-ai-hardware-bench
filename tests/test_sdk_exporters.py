"""Tests for the public SDK, exporters, and self-test."""

from __future__ import annotations

import json
import sqlite3

import pytest

from aihwbench.exporters import (
    CsvExporter,
    MarkdownExporter,
    SqliteExporter,
    get_exporter,
    list_exporters,
)
from aihwbench.sdk import (
    BenchmarkResult,
    BenchmarkRunner,
    MetricSet,
    RegressionReport,
    SystemInfo,
    Workload,
)
from aihwbench.selftest import run_self_test


def _result(run_id: str = "r1") -> dict:
    return {
        "schema_version": "1.0",
        "run_id": run_id,
        "timestamp_utc": "2026-01-01T00:00:00Z",
        "runtime": {"name": "ollama", "version": "0.5.0", "device": "cpu"},
        "model": {"name": "m", "format": "gguf", "quantization": "Q4_K_M"},
        "system": {"os": "windows", "cpu": "Test CPU", "gpu": None},
        "metrics": {"generation_tokens_per_second": 12.5, "ttft_ms": 210.0},
    }


# ---------------------------------------------------------------------------
# SDK
# ---------------------------------------------------------------------------


def test_sdk_roundtrip_preserves_unknown_fields():
    data = _result()
    obj = BenchmarkResult.from_dict(data)
    assert obj.run_id == "r1"
    assert obj.throughput == 12.5
    assert obj.system is not None
    assert obj.runtime is not None
    assert obj.model is not None
    assert obj.metrics is not None


def test_sdk_missing_metrics_stay_none():
    metrics = MetricSet.from_dict({})
    assert metrics.generation_tokens_per_second is None
    assert metrics.ttft_ms is None


def test_sdk_system_info_extra_fields():
    info = SystemInfo.from_dict({"os": "linux", "custom_field": 42})
    assert info.os == "linux"
    assert info.extra["custom_field"] == 42
    d = info.to_dict()
    assert d["custom_field"] == 42


def test_sdk_runner_lists_runtimes():
    runner = BenchmarkRunner()
    assert "ollama" in runner.available_runtimes


def test_sdk_regression_report_from_report():
    class FakeCheck:
        metric = "generation_tokens_per_second"
        status = "PASS"
        baseline = 10.0
        candidate = 11.0
        delta_pct = 10.0
        reason = None

    class FakeReport:
        classification = "IMPROVED"
        status = "PASS"
        checks = [FakeCheck()]

    report = RegressionReport.from_report(FakeReport())
    assert report.classification == "IMPROVED"
    assert report.checks[0].metric == "generation_tokens_per_second"


def test_sdk_workload_defaults():
    w = Workload.from_dict({"id": "chat-short"})
    assert w.id == "chat-short"
    assert w.version == "1.0"


# ---------------------------------------------------------------------------
# Exporters
# ---------------------------------------------------------------------------


def test_all_builtin_exporters_registered():
    names = list_exporters()
    for expected in ("csv", "json", "markdown", "sqlite", "huggingface"):
        assert expected in names


def test_every_exported_exporter_is_reachable():
    """A class in `__all__` that `get_exporter` cannot return is not shipped.

    `ParquetExporter` was defined, exported, and never added to the registry,
    so `get_exporter("parquet")` raised KeyError -- and because nothing could
    reach it, nobody noticed that its `export` also called `pq.Table`, which
    does not exist. Two defects hidden behind one missing registration.
    """
    import aihwbench.exporters as module

    exported = [name for name in module.__all__ if name.endswith("Exporter") and name != "Exporter"]
    registered = set(list_exporters())
    for class_name in exported:
        cls = getattr(module, class_name)
        try:
            instance = cls()
        except RuntimeError:
            continue  # optional extra not installed on this machine
        assert instance.name in registered, (
            f"{class_name} is exported but not registered; "
            f"get_exporter({instance.name!r}) would fail"
        )


def test_parquet_exporter_actually_writes_a_readable_file(tmp_path):
    pytest.importorskip("pyarrow")
    import pyarrow.parquet as pq

    out = tmp_path / "out.parquet"
    get_exporter("parquet").export([_result("r1"), _result("r2")], out)

    table = pq.read_table(out)
    assert table.num_rows == 2
    assert table.column("run_id").to_pylist() == ["r1", "r2"]


def test_huggingface_export_is_loadable_layout(tmp_path):
    """The card is the point: data without one is a file, not a dataset."""
    out = tmp_path / "hf"
    get_exporter("huggingface").export([_result("r1"), _result("r2")], out)

    data = out / "data" / "train.jsonl"
    assert data.is_file()
    rows = [json.loads(line) for line in data.read_text(encoding="utf-8").splitlines()]
    assert [r["run_id"] for r in rows] == ["r1", "r2"]

    card = (out / "README.md").read_text(encoding="utf-8")
    assert card.startswith("---")
    assert "license: apache-2.0" in card
    # The loader needs the path in the front-matter to match what was written.
    assert "path: data/train.jsonl" in card


def test_huggingface_card_warns_against_ranking_across_groups(tmp_path):
    """The dataset travels away from this repository; the caveat must travel too.

    Someone loading it from the Hub has none of the project's context, and a
    flat table sorted by throughput is exactly the false comparison the
    classifier exists to prevent.
    """
    out = tmp_path / "hf"
    get_exporter("huggingface").export([_result("r1")], out)
    card = (out / "README.md").read_text(encoding="utf-8")

    assert "not necessarily comparable" in card
    assert "comparability" in card
    assert "Missing values are missing, not zero" in card


def test_huggingface_export_needs_no_optional_dependency(tmp_path, monkeypatch):
    """It must work on the minimal machines most likely to want it."""
    import builtins

    real_import = builtins.__import__

    def no_pyarrow(name, *args, **kwargs):
        if name.startswith("pyarrow"):
            raise ImportError("pyarrow is unavailable in this test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_pyarrow)
    out = tmp_path / "hf"
    get_exporter("huggingface").export([_result("r1")], out)
    assert (out / "data" / "train.jsonl").is_file()


def test_json_exporter_writes_results(tmp_path):
    out = tmp_path / "out.json"
    written = get_exporter("json").export([_result()], out)
    loaded = json.loads(written.read_text(encoding="utf-8"))
    assert loaded[0]["run_id"] == "r1"


def test_csv_exporter_columns_and_empty_values(tmp_path):
    out = tmp_path / "out.csv"
    CsvExporter().export([_result(), {"run_id": "empty"}], out)
    lines = out.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3  # header + 2 rows
    assert "run_id" in lines[0]
    # Missing metrics stay empty, never fabricated zeros.
    assert ",," in lines[2]


def test_markdown_exporter_table(tmp_path):
    out = tmp_path / "out.md"
    MarkdownExporter().export([_result()], out)
    text = out.read_text(encoding="utf-8")
    assert text.startswith("| run_id")
    assert "| r1 |" in text or "| r1" in text


def test_sqlite_exporter_queryable(tmp_path):
    out = tmp_path / "out.db"
    SqliteExporter().export([_result()], out)
    conn = sqlite3.connect(out)
    try:
        rows = conn.execute("SELECT run_id, runtime FROM results").fetchall()
    finally:
        conn.close()
    assert rows == [("r1", "ollama")]


def test_unknown_exporter_raises():
    with pytest.raises(KeyError):
        get_exporter("nope")


def test_parquet_exporter_requires_extra():
    from aihwbench.exporters import ParquetExporter

    try:
        import pyarrow  # noqa: F401

        pytest.skip("pyarrow installed; failure path not applicable")
    except ImportError:
        pass
    with pytest.raises(RuntimeError):
        ParquetExporter()


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------


def test_self_test_returns_structured_report():
    report = run_self_test()
    assert report["overall"] in ("pass", "warn", "fail")
    checks = {c["check"] for c in report["checks"]}
    assert "timer_resolution" in checks
    assert "runtimes" in checks
    for c in report["checks"]:
        assert c["status"] in ("pass", "warn", "skip", "fail")
        assert isinstance(c["detail"], str) and c["detail"]
    total = (
        report["summary"]["pass"]
        + report["summary"]["warn"]
        + report["summary"]["skip"]
        + report["summary"]["fail"]
    )
    assert total == len(report["checks"])
