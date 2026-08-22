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
from .trust import trust_state

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


def load_results(directory: Path) -> list[dict[str, Any]]:
    """Load all valid result JSON files from a directory."""
    results = []
    for path in sorted(directory.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict) and not validate_result(data):
            results.append(data)
    return results


def _row(result: dict[str, Any]) -> dict[str, Any]:
    system = result.get("system", {})
    runtime = result.get("runtime", {})
    model = result.get("model", {})
    metrics = result.get("metrics", {})
    repro = result.get("reproducibility", {})
    return {
        "run_id": result.get("run_id"),
        "timestamp": result.get("timestamp"),
        "trust": trust_state(repro.get("trust")),
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


def export_dataset(results_dir: Path, output_dir: Path) -> list[Path]:
    """Generate index.json, dataset.csv, LEADERBOARD.md from results."""
    results = load_results(results_dir)
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
