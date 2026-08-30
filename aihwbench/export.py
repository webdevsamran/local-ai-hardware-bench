"""Dataset and leaderboard generation from published results.

Reads validated result documents from a directory and produces:
- ``index.json``: machine-readable summary of every result
- ``dataset.csv``: flat table for spreadsheets/analysis
- ``LEADERBOARD.md``: human-readable throughput view

Only schema-valid results are included. Trust states are surfaced but
never fabricated.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .schemas import validate_result
from .trust import effective_trust

_DATASET_COLUMNS = [
    "run_id",
    "timestamp",
    "trust",
    "os",
    "cpu",
    "gpu",
    "gpu_vram_mb",
    "npu",
    "runtime",
    "runtime_version",
    "backend",
    "device",
    "model",
    "format",
    "quantization",
    "checksum",
    "load_time_ms",
    "ttft_ms",
    "prompt_tokens_per_second",
    "generation_tokens_per_second",
    "total_latency_ms",
    "p50_latency_ms",
    "p95_latency_ms",
    "peak_ram_mb",
    "peak_vram_mb",
    "avg_cpu_util_percent",
    "avg_gpu_util_percent",
    "max_temperature_c",
    "average_power_watts",
    "performance_per_watt",
]


def load_results(directory: Path, *, strict: bool = False) -> list[dict[str, Any]]:
    """Load result JSON files from a directory.

    Lenient by default (exploratory local use): files that are unreadable
    or fail schema validation are skipped. When ``strict=True``
    (publishing/CI paths), any unreadable or schema-invalid file raises
    ``DatasetLoadError`` with every offending path — silent data loss is
    never acceptable when generating published artifacts.
    """
    problems: list[str] = []
    results = []
    for path in sorted(directory.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            problems.append(f"unreadable or invalid JSON: {path}: {exc}")
            continue
        if not isinstance(data, dict):
            problems.append(f"not an object: {path}")
            continue
        errors = validate_result(data)
        if errors:
            problems.append(f"schema validation failed: {path}: {'; '.join(errors[:3])}")
            continue
        results.append(data)
    if strict and problems:
        raise DatasetLoadError(
            f"refusing to load dataset from {directory}: "
            f"{len(problems)} file(s) are unreadable or invalid:\n" + "\n".join(problems)
        )
    return results


class DatasetLoadError(ValueError):
    """Raised when a published-dataset load fails closed (strict mode)."""


def _row(result: dict[str, Any]) -> dict[str, Any]:
    system = result.get("system", {})
    runtime = result.get("runtime", {})
    model = result.get("model", {})
    metrics = result.get("metrics", {})
    return {
        "run_id": result.get("run_id"),
        "timestamp": result.get("timestamp"),
        "trust": effective_trust(result),
        "os": system.get("os"),
        "cpu": system.get("cpu"),
        "gpu": system.get("gpu"),
        "gpu_vram_mb": system.get("gpu_vram_mb"),
        "npu": system.get("npu"),
        "runtime": runtime.get("name"),
        "runtime_version": runtime.get("version"),
        "backend": runtime.get("backend"),
        "device": runtime.get("device"),
        "model": model.get("name"),
        "format": model.get("format"),
        "quantization": model.get("quantization"),
        "checksum": model.get("checksum"),
        **{k: metrics.get(k) for k in _DATASET_COLUMNS[16:]},
    }


def export_dataset(results_dir: Path, output_dir: Path, *, strict: bool = False) -> list[Path]:
    """Generate index.json, dataset.csv, LEADERBOARD.md from results.

    ``strict=True`` makes the load fail closed (publishing/CI); the default
    is tolerant for exploratory local use.
    """
    results = load_results(results_dir, strict=strict)
    rows = [_row(r) for r in results]
    output_dir.mkdir(parents=True, exist_ok=True)

    index_path = output_dir / "index.json"
    index_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "source": str(results_dir),
                "count": len(rows),
                "results": rows,
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    csv_path = output_dir / "dataset.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=_DATASET_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    md_path = output_dir / "LEADERBOARD.md"
    lines = [
        "# AIHWBench Leaderboard",
        "",
        f"Generated from {len(rows)} validated result(s) in `{results_dir}`.",
        "",
        "| Run | Runtime | Model | GPU | Gen tok/s | TTFT ms | Perf/W |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in rows:
        lines.append(
            f"| {r['run_id']} | {r['runtime']} | {r['model']} | {r['gpu']} "
            f"| {r['generation_tokens_per_second']} | {r['ttft_ms']} "
            f"| {r['performance_per_watt']} |"
        )
    lines.append("")
    lines.append(
        "> Only schema-validated results are listed. Cross-runtime comparisons "
        "require identical workloads; see docs/methodology.md."
    )
    md_path.write_text(chr(10).join(lines), encoding="utf-8")

    return [index_path, csv_path, md_path]


def export_parquet(results, output_path):
    """Write the flattened results view as Parquet (#17).

    ``results`` may be a results directory (``*.json`` files are loaded,
    fail-closed) or an in-memory sequence of result documents. Requires
    the optional ``parquet`` extra (pyarrow). A missing dependency or a
    corrupted result raises instead of silently skipping; missing metrics
    stay null and nothing is fabricated.
    """
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise RuntimeError(
            "Parquet export requires the 'parquet' extra: pip install 'aihwbench[parquet]'"
        ) from exc

    if isinstance(results, (str, Path)):
        src = Path(results)
        docs = []
        for path in sorted(src.glob("*.json")):
            try:
                docs.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError) as exc:
                raise ValueError(f"unreadable result {path.name}: {exc}") from exc
        if not docs:
            raise ValueError(f"no result JSON files found in {src}")
    else:
        docs = list(results)
        if not docs:
            raise ValueError("no results provided")
    rows = [_flatten_result_row(doc) for doc in docs]
    keys = sorted({k for row in rows for k in row})
    table = pa.table({k: [row.get(k) for row in rows] for k in keys})
    dst = Path(output_path)
    dst.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, dst)
    return dst


def _flatten_result_row(doc):
    """One flat row per result; only scalar block fields are projected."""
    row = {
        "run_id": doc.get("run_id"),
        "schema_version": doc.get("schema_version"),
        "timestamp": doc.get("timestamp"),
    }
    for section in ("system", "runtime", "model", "metrics", "reproducibility"):
        sub = doc.get(section)
        if not isinstance(sub, dict):
            continue
        for k, v in sub.items():
            if isinstance(v, (str, int, float, bool)) or v is None:
                row[f"{section}_{k}"] = v
    ts = doc.get("trust_state") or (doc.get("reproducibility") or {}).get("trust")
    row["trust_state"] = ts
    return row
