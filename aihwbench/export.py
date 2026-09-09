"""Dataset and leaderboard generation from published results.

Reads validated result documents from a directory and produces:
- ``index.json``: machine-readable summary of every result
- ``dataset.csv``: flat table for spreadsheets/analysis
- ``LEADERBOARD.md``: human-readable throughput view

Only schema-valid results are included. Trust states are surfaced but
never fabricated.

The leaderboard is grouped by comparison safety rather than presented as
one ranked table. A single table with a throughput column invites the
reader to rank every row against every other, which the comparison-safety
classifier says is invalid for most pairs -- a prose footnote does not undo
the visual claim a shared column makes.
"""

from __future__ import annotations

import csv
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .comparability import NOT_COMPARABLE, compare_classification
from .metrics import performance_per_watt_unit
from .quality import MIN_PUBLISHED_ITERATIONS, MIN_WARMUP_RUNS, statistical_confidence
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


def comparison_groups(results: Sequence[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Partition results into mutually-comparable cliques.

    A result joins a group only when it is comparable with *every* member,
    not merely with the first: comparability is not transitive, so a
    representative-only check would build groups containing pairs the
    classifier rejects. Order is stable, so the grouping is deterministic.
    """
    groups: list[list[dict[str, Any]]] = []
    for result in results:
        for group in groups:
            if all(
                compare_classification(result, member)["classification"] != NOT_COMPARABLE
                for member in group
            ):
                group.append(result)
                break
        else:
            groups.append([result])
    return groups


def group_label(group: Sequence[dict[str, Any]]) -> str:
    """Describe what the members of a comparable group share."""
    first = group[0]
    model = (first.get("model") or {}).get("name") or "unknown model"
    quant = (first.get("model") or {}).get("quantization")
    runtime = (first.get("runtime") or {}).get("name") or "unknown runtime"
    backend = (first.get("runtime") or {}).get("backend")
    device = (first.get("runtime") or {}).get("device")
    parts = [str(model)]
    if quant:
        parts.append(str(quant))
    detail = "/".join(str(p) for p in (backend, device) if p)
    runtime_text = f"{runtime} ({detail})" if detail else str(runtime)
    return f"{' '.join(parts)} on {runtime_text}"


def _num(value: object, places: int = 3) -> str:
    """Render a metric for the leaderboard.

    Floats are rounded to ``places`` significant decimals. Publishing
    ``13.48542600896861`` from a division of two 2-decimal inputs implies
    precision that was never measured. ``None`` stays visible as "not
    measured" rather than being dropped or interpolated.
    """
    if value is None:
        return "not measured"
    if isinstance(value, float):
        return f"{value:,.{places}f}".rstrip("0").rstrip(".")
    return str(value)


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
    by_run = {r["run_id"]: r for r in rows}
    groups = comparison_groups(results)
    rankable = [g for g in groups if len(g) > 1]

    lines = [
        "# AIHWBench Leaderboard",
        "",
        f"Generated from {len(rows)} validated result(s) in `{results_dir.as_posix()}`.",
        "",
        "Results are grouped by the comparison-safety classifier "
        "(`aihwbench/comparability.py`), and **ranking is meaningful only "
        "within a group**. Putting every result in one table under a shared "
        "throughput column invites a comparison the classifier rejects for "
        "most pairs, and a footnote does not undo the claim the column makes.",
        "",
    ]
    if rankable:
        lines.append(
            f"{len(groups)} comparable group(s); {len(rankable)} contain more "
            "than one result and can be ranked."
        )
    else:
        lines.append(
            f"**No two published results are comparable yet**: {len(rows)} "
            f"result(s) form {len(groups)} group(s) of one. Each is a single "
            "measurement, not a ranking. Comparable results arrive when the "
            "same model and runtime are benchmarked on other hardware — see "
            "[docs/hardware-needed.md](../../docs/hardware-needed.md)."
        )
    lines.append("")

    for group in groups:
        lines.append(f"## {group_label(group)}")
        lines.append("")
        if len(group) == 1:
            lines.append("*Single result — nothing to compare it against yet.*")
            lines.append("")
        # Rank within the group by generation throughput where it was measured;
        # unmeasured rows keep their order rather than sorting as zero.
        ordered = sorted(
            group,
            key=lambda d: (
                (d.get("metrics") or {}).get("generation_tokens_per_second") is None,
                -((d.get("metrics") or {}).get("generation_tokens_per_second") or 0.0),
            ),
        )
        lines.append("| Run | GPU | Gen tok/s | TTFT ms | Perf/W | Perf/W unit | Runs | Trust |")
        lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
        for result in ordered:
            row = by_run[result.get("run_id")]
            # The published policy is 5 measured iterations after 2 warm-ups.
            # A single-run number renders identically to a five-iteration
            # median, so anything short of the policy is marked rather than
            # left looking like the rest.
            confidence = statistical_confidence(result)
            runs = (
                str(confidence["iterations"])
                if confidence["meets_policy"]
                else f"**{confidence['label'].replace('_', ' ')}**"
            )
            # Perf/W is tok/s/W for generative runtimes and inf/s/W for graph
            # ones. The unit is published alongside the number: without it the
            # column silently mixes two different quantities.
            unit = performance_per_watt_unit(result.get("metrics") or {})
            lines.append(
                f"| {row['run_id']} | {row['gpu']} "
                f"| {_num(row['generation_tokens_per_second'])} | {_num(row['ttft_ms'])} "
                f"| {_num(row['performance_per_watt'])} | {unit} | {runs} "
                f"| {row['trust']} |"
            )
        lines.append("")

    lines.append(
        "> Only schema-validated results are listed. Groups are cliques under "
        "the comparison-safety classifier: every member is comparable with "
        "every other member, not merely with the first."
    )
    lines.append(
        "> **Perf/W is not one quantity.** `tok/s/W` rows are generative "
        "throughput per watt; `inf/s/W` rows are inferences per watt. They "
        "are not comparable to each other."
    )
    lines.append(
        "> **Runs** is the measured iteration count. The published policy is "
        f"{MIN_PUBLISHED_ITERATIONS} iterations after {MIN_WARMUP_RUNS} "
        "warm-ups; anything short of it is marked, because a single "
        "measurement renders identically to a five-iteration median."
    )
    md_path.write_text(chr(10).join(lines) + chr(10), encoding="utf-8")

    return [index_path, csv_path, md_path]


def export_parquet(results: Sequence[dict[str, Any]] | str | Path, output_path: str | Path) -> Path:
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


def _flatten_result_row(doc: dict[str, Any]) -> dict[str, Any]:
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
