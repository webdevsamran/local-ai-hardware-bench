"""Exporter architecture (#47).

Exporters convert a list of result documents into a serialized format.
Built-ins: JSON, CSV, Markdown, SQLite (stdlib). Parquet is available
only when pyarrow is installed (optional extra) — heavy dependencies
stay behind extras.

Third-party exporters publish via the ``aihwbench.exporters``
entry-point group; each entry point resolves to an ``Exporter`` subclass
(or instance) with ``name`` and ``export(results, out_path) -> Path``.
"""

from __future__ import annotations

import csv
import importlib.metadata
import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Protocol

__all__ = [
    "Exporter",
    "JsonExporter",
    "CsvExporter",
    "MarkdownExporter",
    "SqliteExporter",
    "ParquetExporter",
    "get_exporter",
    "list_exporters",
    "discover_exporter_plugins",
]

ENTRY_POINT_GROUP = "aihwbench.exporters"

# Flat columns used by tabular exporters. Column names are the canonical
# metric ids (see aihwbench/metrics.py METRIC_REGISTRY). Missing values
# stay empty — never fabricated zeros.
CSV_COLUMNS = (
    "run_id",
    "timestamp",
    "runtime",
    "runtime_version",
    "device",
    "model",
    "format",
    "quantization",
    "os",
    "cpu",
    "gpu",
    "generation_tokens_per_second",
    "prompt_tokens_per_second",
    "ttft_ms",
    "p50_latency_ms",
    "p95_latency_ms",
    "p99_latency_ms",
    "peak_vram_mb",
    "peak_ram_mb",
    "average_power_watts",
)

# Metric columns resolved through the canonical registry (alias-tolerant).
_METRIC_COLUMNS = frozenset(
    {
        "generation_tokens_per_second",
        "prompt_tokens_per_second",
        "ttft_ms",
        "p50_latency_ms",
        "p95_latency_ms",
        "p99_latency_ms",
        "peak_vram_mb",
        "peak_ram_mb",
        "average_power_watts",
    }
)


class Exporter(Protocol):
    name: str

    def export(self, results: list[dict[str, Any]], out_path: Path) -> Path: ...


def _flat_row(result: dict[str, Any]) -> dict[str, Any]:
    runtime = result.get("runtime") or {}
    model = result.get("model") or {}
    system = result.get("system") or {}
    metrics = result.get("metrics") or {}
    from ..metrics import _MISSING, resolve_metric

    timestamp = result.get("timestamp")
    if timestamp is None:
        timestamp = result.get("timestamp_utc")  # legacy key, read-only
    metrics_row: dict[str, Any] = {}
    for k in _METRIC_COLUMNS:
        value = resolve_metric(metrics, k)
        metrics_row[k] = None if value is _MISSING else value
    return {
        "run_id": result.get("run_id"),
        "timestamp": timestamp,
        "runtime": runtime.get("name"),
        "runtime_version": runtime.get("version"),
        "device": runtime.get("device"),
        "model": model.get("name"),
        "format": model.get("format"),
        "quantization": model.get("quantization"),
        "os": system.get("os"),
        "cpu": system.get("cpu"),
        "gpu": system.get("gpu"),
        **metrics_row,
    }


class JsonExporter:
    name = "json"

    def export(self, results: list[dict[str, Any]], out_path: Path) -> Path:
        out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
        return out_path


class CsvExporter:
    name = "csv"

    def export(self, results: list[dict[str, Any]], out_path: Path) -> Path:
        rows = [_flat_row(r) for r in results]
        with open(out_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(CSV_COLUMNS))
            writer.writeheader()
            writer.writerows(rows)
        return out_path


class MarkdownExporter:
    name = "markdown"

    def export(self, results: list[dict[str, Any]], out_path: Path) -> Path:
        rows = [_flat_row(r) for r in results]
        cols = (
            "run_id",
            "runtime",
            "model",
            "quantization",
            "generation_tokens_per_second",
            "ttft_ms",
        )
        lines = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
        for row in rows:
            cells = ["" if row.get(c) is None else str(row[c]) for c in cols]
            lines.append("| " + " | ".join(cells) + " |")
        out_path.write_text(chr(10).join(lines) + chr(10), encoding="utf-8")
        return out_path


class SqliteExporter:
    name = "sqlite"

    def export(self, results: list[dict[str, Any]], out_path: Path) -> Path:
        if out_path.exists():
            out_path.unlink()
        conn = sqlite3.connect(out_path)
        try:
            cols = list(CSV_COLUMNS)
            quoted = ", ".join('"' + c + '"' for c in cols)
            conn.execute(f"CREATE TABLE results ({quoted})")
            rows = [[_flat_row(r).get(c) for c in cols] for r in results]
            placeholders = ", ".join("?" for _ in cols)
            conn.executemany(f"INSERT INTO results VALUES ({placeholders})", rows)
            conn.commit()
        finally:
            conn.close()
        return out_path


class ParquetExporter:
    """Optional parquet support via pyarrow (extras: parquet)."""

    name = "parquet"

    def __init__(self) -> None:
        try:
            import pyarrow  # noqa: F401
            import pyarrow.parquet as pq
        except ImportError as exc:
            raise RuntimeError(
                "parquet exporter requires the 'parquet' extra: pip install aihwbench[parquet]"
            ) from exc
        self._pq = pq

    def export(self, results: list[dict[str, Any]], out_path: Path) -> Path:
        rows = [_flat_row(r) for r in results]
        table = self._pq.Table.from_pylist(rows)
        self._pq.write_table(table, out_path)
        return out_path


_BUILTIN_EXPORTER_CLASSES = (
    JsonExporter,
    CsvExporter,
    MarkdownExporter,
    SqliteExporter,
)


def _build_registry() -> dict[str, Exporter]:
    registry: dict[str, Exporter] = {}
    for cls in _BUILTIN_EXPORTER_CLASSES:
        instance = cls()
        registry[instance.name] = instance
    return registry


_REGISTRY = _build_registry()
_PLUGINS_DISCOVERED = False


def get_exporter(name: str) -> Exporter:
    _ensure_plugins()
    try:
        return _REGISTRY[name]
    except KeyError:
        known = ", ".join(sorted(_REGISTRY)) or "<none>"
        raise KeyError(f"unknown exporter {name!r}; registered: {known}") from None


def list_exporters() -> list[str]:
    _ensure_plugins()
    return sorted(_REGISTRY)


def discover_exporter_plugins() -> Iterator[tuple[str, Exporter]]:
    global _PLUGINS_DISCOVERED
    eps = importlib.metadata.entry_points()
    try:
        group = eps.select(group=ENTRY_POINT_GROUP)
    except AttributeError:
        group = eps.get(ENTRY_POINT_GROUP, [])  # type: ignore[attr-defined]
    for ep in group:
        try:
            obj = ep.load()
            exporter = obj() if callable(obj) and not hasattr(obj, "name") else obj
            if hasattr(exporter, "name") and hasattr(exporter, "export"):
                _REGISTRY[exporter.name] = exporter
                yield exporter.name, exporter
        except Exception:
            continue
    _PLUGINS_DISCOVERED = True


def _ensure_plugins() -> None:
    if not _PLUGINS_DISCOVERED:
        for _ in discover_exporter_plugins():
            pass
