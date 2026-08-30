"""Tests for canonical metric IDs, alias resolution, exporter columns,
and SDK parsing — Fix 10 (metric-name drift)."""

from __future__ import annotations

import csv
import sqlite3

from aihwbench.exporters import CSV_COLUMNS, CsvExporter, SqliteExporter, _flat_row
from aihwbench.metrics import (
    _MISSING,
    METRIC_REGISTRY,
    aggregate_iteration_metrics,
    has_metric,
    resolve_metric,
)
from aihwbench.sdk import MetricSet


def _iterations() -> list[dict]:
    return [
        {
            "ttft_ms": 100.0,
            "total_latency_ms": 500.0,
            "completion_tokens": 48,
            "eval_seconds": 0.4,
            "prompt_tokens": 20,
            "prompt_eval_seconds": 0.1,
            "average_power_watts": 20.0,
        },
        {
            "ttft_ms": 110.0,
            "total_latency_ms": 520.0,
            "completion_tokens": 52,
            "eval_seconds": 0.5,
            "prompt_tokens": 20,
            "prompt_eval_seconds": 0.11,
            "average_power_watts": 21.0,
        },
    ]


# ---------------------------------------------------------------------------
# Registry + resolver
# ---------------------------------------------------------------------------


def test_registry_covers_every_documented_metric():
    # Canonical ids must be unique.
    assert len(METRIC_REGISTRY) == len(set(METRIC_REGISTRY))
    # Every entry declares a unit and a family.
    for _cid, meta in METRIC_REGISTRY.items():
        assert "unit" in meta and meta["unit"]
        assert "family" in meta and meta["family"]
        assert isinstance(meta["aliases"], tuple)


def test_resolve_canonical_and_legacy_alias():
    metrics = {"p95_latency_ms": 12.3}
    assert resolve_metric(metrics, "p95_latency_ms") == 12.3

    legacy = {"latency_p95_ms": 9.7}
    assert resolve_metric(legacy, "p95_latency_ms") == 9.7
    assert has_metric(legacy, "p95_latency_ms")

    # Absent metric returns the sentinel, not None.
    assert resolve_metric(metrics, "itl_ms") is _MISSING
    # Explicit null stays null (distinct from absent).
    assert resolve_metric({"itl_ms": None}, "itl_ms") is None


def test_documented_legacy_alias_pairs():
    assert "itl_mean_ms" in METRIC_REGISTRY["itl_ms"]["aliases"]
    assert "energy_per_token_joules" in METRIC_REGISTRY["energy_joules_per_token"]["aliases"]
    assert "latency_stddev_ms" in METRIC_REGISTRY["stddev_latency_ms"]["aliases"]


# ---------------------------------------------------------------------------
# Aggregator emits canonical names only
# ---------------------------------------------------------------------------


def test_aggregator_emits_canonical_names():
    out = aggregate_iteration_metrics(_iterations())
    assert "stddev_latency_ms" in out
    assert "min_latency_ms" in out
    assert "max_latency_ms" in out
    assert "ci95_latency_ms" in out
    assert "itl_ms" in out
    assert "energy_joules_per_token" in out
    # No legacy names are emitted.
    for legacy in (
        "latency_stddev_ms",
        "latency_min_ms",
        "latency_max_ms",
        "latency_ci95_ms",
        "itl_mean_ms",
        "energy_per_token_joules",
        "latency_p95_ms",
    ):
        assert legacy not in out


def test_aggregator_values_match_under_resolver():
    out = aggregate_iteration_metrics(_iterations())
    assert resolve_metric(out, "energy_joules_per_token") == out["energy_joules_per_token"]


# ---------------------------------------------------------------------------
def test_csv_populates_latency_columns(tmp_path):
    out = tmp_path / "out.csv"
    CsvExporter().export([_doc()], out)
    with open(out, encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 1
    assert rows[0]["timestamp"] == "2026-01-01T00:00:00Z"
    assert rows[0]["p50_latency_ms"] == "2.0"
    assert rows[0]["p95_latency_ms"] == "3.1"
    assert rows[0]["p99_latency_ms"] == "4.0"


def test_csv_reads_legacy_alias_metrics(tmp_path):
    # A document that still uses the old exporter vocabulary must not lose
    # data when exported.
    out = tmp_path / "out.csv"
    doc = _doc()
    doc["metrics"] = {
        "generation_tokens_per_second": 12.5,
        "latency_p95_ms": 7.7,
    }
    CsvExporter().export([doc], out)
    with open(out, encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert rows[0]["p95_latency_ms"] == "7.7"


def test_csv_reads_legacy_timestamp_key(tmp_path):
    out = tmp_path / "out.csv"
    doc = _doc()
    doc["timestamp_utc"] = "2020-05-05T00:00:00Z"
    doc.pop("timestamp", None)
    CsvExporter().export([doc], out)
    with open(out, encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert rows[0]["timestamp"] == "2020-05-05T00:00:00Z"


def test_sqlite_uses_canonical_columns(tmp_path):
    out = tmp_path / "out.db"
    SqliteExporter().export([_doc()], out)
    conn = sqlite3.connect(out)
    try:
        col = conn.execute("SELECT p95_latency_ms FROM results").fetchone()
        names = [r[1] for r in conn.execute("PRAGMA table_info(results)")]
    finally:
        conn.close()
    assert col == (3.1,)
    assert "latency_p95_ms" not in names
    assert "p95_latency_ms" in names


def test_flat_row_maps_missing_metrics_to_none():
    row = _flat_row({"metrics": {"p95_latency_ms": 5.0}})
    assert row["p95_latency_ms"] == 5.0
    assert row["p50_latency_ms"] is None
    assert row["generation_tokens_per_second"] is None


# ---------------------------------------------------------------------------
# SDK parses canonical + legacy metric names
# ---------------------------------------------------------------------------


def test_sdk_metricset_parses_canonical():
    ms = MetricSet.from_dict({"p50_latency_ms": 2.0, "p95_latency_ms": 3.0})
    assert ms.p50_latency_ms == 2.0
    assert ms.p95_latency_ms == 3.0
    assert hasattr(ms, "p50_latency_ms")
    assert not hasattr(ms, "latency_p50_ms")


def test_sdk_metricset_parses_legacy_aliases():
    ms = MetricSet.from_dict({"latency_p95_ms": 9.9, "energy_per_token_joules": 0.5})
    assert ms.p95_latency_ms == 9.9
    assert ms.energy_joules_per_token == 0.5


def test_sdk_metricset_missing_and_null():
    ms = MetricSet.from_dict({"p95_latency_ms": None})
    assert ms.p95_latency_ms is None
    ms2 = MetricSet.from_dict({})
    assert ms2.p95_latency_ms is None


# Exporters use canonical columns and populate them
# ---------------------------------------------------------------------------


def _doc(p95: float = 3.1) -> dict:
    return {
        "run_id": "r1",
        "timestamp": "2026-01-01T00:00:00Z",
        "runtime": {"name": "ollama", "version": "0.5.0", "device": "cpu"},
        "model": {"name": "m"},
        "system": {"os": "linux"},
        "metrics": {
            "generation_tokens_per_second": 12.5,
            "p50_latency_ms": 2.0,
            "p95_latency_ms": p95,
            "p99_latency_ms": 4.0,
        },
    }


def test_csv_columns_are_canonical():
    assert "p50_latency_ms" in CSV_COLUMNS
    assert "p95_latency_ms" in CSV_COLUMNS
    assert "p99_latency_ms" in CSV_COLUMNS
    assert "timestamp" in CSV_COLUMNS
    for legacy in ("latency_p50_ms", "latency_p95_ms", "latency_p99_ms", "timestamp_utc"):
        assert legacy not in CSV_COLUMNS
