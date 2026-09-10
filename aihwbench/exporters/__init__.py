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
    "HuggingFaceExporter",
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
            import pyarrow
            import pyarrow.parquet as pq
        except ImportError as exc:
            raise RuntimeError(
                "parquet exporter requires the 'parquet' extra: pip install aihwbench[parquet]"
            ) from exc
        # `Table` lives in `pyarrow`, not `pyarrow.parquet`. Holding both is
        # what the export actually needs; reaching for `pq.Table` raised
        # AttributeError on every call, which nothing noticed because this
        # exporter was never added to the registry and so was never called.
        self._pa = pyarrow
        self._pq = pq

    def export(self, results: list[dict[str, Any]], out_path: Path) -> Path:
        rows = [_flat_row(r) for r in results]
        table = self._pa.Table.from_pylist(rows)
        self._pq.write_table(table, out_path)
        return out_path


class HuggingFaceExporter:
    """A directory `datasets.load_dataset()` can open, plus its dataset card.

    Unlike the other exporters this writes a *directory*, because a
    HuggingFace dataset is not one file: it is data plus a card whose YAML
    front-matter declares the licence, the column types and the configs. A
    bare parquet file uploaded without that card loads as an untyped table
    with no stated licence, which is the difference between publishing a
    dataset and dropping a file somewhere.

    Nothing is uploaded and no network call is made. This produces the files;
    pushing them is the maintainer's deliberate act, with their credentials.

    Data lands as JSON Lines rather than parquet so the export works with no
    optional dependency at all -- `datasets` reads both, and an export that
    silently needs pyarrow would be unavailable exactly on the minimal
    machines most likely to want it.
    """

    name = "huggingface"

    #: What each column means. Written into the card so a consumer who never
    #: reads this repository still learns that the rate is wall-clock and that
    #: rank is meaningless across comparison groups.
    FIELD_NOTES = {
        "generation_tokens_per_second": (
            "Tokens generated per second. For HTTP-server runtimes this is "
            "measured over the client wall-clock decode window and includes "
            "the HTTP stack; it is not an in-process engine counter."
        ),
        "ttft_ms": "Time to first token, in milliseconds, including queueing.",
        "average_power_watts": (
            "Mean power draw during the run. GPU package power where a GPU "
            "probe answered, CPU package power (RAPL) otherwise."
        ),
        "peak_vram_mb": "Peak GPU memory in use, as reported by the vendor tool.",
        "quantization": "Model quantization, where the runtime reports one; null otherwise.",
    }

    def export(self, results: list[dict[str, Any]], out_path: Path) -> Path:
        out_path.mkdir(parents=True, exist_ok=True)
        data_dir = out_path / "data"
        data_dir.mkdir(exist_ok=True)

        rows = [_flat_row(r) for r in results]
        data_file = data_dir / "train.jsonl"
        with open(data_file, "w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False) + chr(10))

        (out_path / "README.md").write_text(self._card(rows), encoding="utf-8")
        return out_path

    def _card(self, rows: list[dict[str, Any]]) -> str:
        runtimes = sorted({r["runtime"] for r in rows if r.get("runtime")})
        models = sorted({r["model"] for r in rows if r.get("model")})

        # Front-matter drives what HuggingFace shows and how the data loads.
        lines = [
            "---",
            "license: apache-2.0",
            "pretty_name: AIHWBench local AI hardware benchmarks",
            "tags:",
            "- benchmark",
            "- local-inference",
            "- hardware",
            "configs:",
            "- config_name: default",
            "  data_files:",
            "  - split: train",
            "    path: data/train.jsonl",
            "---",
            "",
            "# AIHWBench results",
            "",
            "Measured local AI inference benchmarks: throughput, latency, memory,",
            "power and thermals, on consumer hardware, with the raw result",
            "documents published alongside.",
            "",
            f"- Rows: {len(rows)}",
            f"- Runtimes: {', '.join(runtimes) if runtimes else 'none'}",
            f"- Models: {', '.join(models) if models else 'none'}",
            "",
            "## Reading this data honestly",
            "",
            "**Two rows are not necessarily comparable.** Results are comparable",
            "only when the model, quantization, runtime, backend, device and the",
            "whole measurement protocol match. Sorting this table by",
            '`generation_tokens_per_second` and reading the top row as "fastest"',
            "compares different experiments and reports the difference as a",
            "performance gap. The rules are published and machine-readable at",
            "`data/comparability.json` in the project's dataset API, and the",
            "classifier that applies them is `aihwbench/comparability.py`.",
            "",
            "**Missing values are missing, not zero.** A null means the figure",
            "could not be measured on that platform. Nothing here is estimated.",
            "",
            "## Columns",
            "",
        ]
        for column in CSV_COLUMNS:
            note = self.FIELD_NOTES.get(column)
            lines.append(f"- `{column}`" + (f" — {note}" if note else ""))
        lines += [
            "",
            "## Provenance",
            "",
            "Generated by `aihwbench export-as --format huggingface` from the",
            "result documents in `results/published/`. Each row flattens one",
            "result; the full document, including its telemetry trace, energy",
            "block and provenance hashes, is in the source repository.",
            "",
            "## Licence",
            "",
            "Apache-2.0, same as the project.",
        ]
        return chr(10).join(lines) + chr(10)


_BUILTIN_EXPORTER_CLASSES = (
    JsonExporter,
    CsvExporter,
    MarkdownExporter,
    SqliteExporter,
    HuggingFaceExporter,
)


#: Exporters whose dependencies are optional. Constructing one raises
#: RuntimeError when its extra is not installed, so it is offered only where
#: it would actually work -- `list_exporters` then tells the truth about this
#: machine rather than advertising a format that errors on use.
_OPTIONAL_EXPORTER_CLASSES = (ParquetExporter,)


def _build_registry() -> dict[str, Exporter]:
    registry: dict[str, Exporter] = {}
    for cls in _BUILTIN_EXPORTER_CLASSES:
        instance = cls()
        registry[instance.name] = instance
    for optional in _OPTIONAL_EXPORTER_CLASSES:
        try:
            extra: Exporter = optional()
        except RuntimeError:
            continue  # extra not installed; not offered rather than broken
        registry[extra.name] = extra
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
