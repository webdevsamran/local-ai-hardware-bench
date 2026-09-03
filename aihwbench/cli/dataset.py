"""Dataset and data-quality commands: export views, named exporters,
quality evaluators, quantization comparison, anomaly flags and snapshots."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..dataset_versioning import build_snapshot_manifest
from ..evaluators import list_evaluators, load_dataset, run_evaluation
from ..exit_codes import EXIT_OK, EXIT_USAGE_ERROR, EXIT_VALIDATION_ERROR
from ..export import DatasetLoadError, export_dataset, export_parquet
from ..exporters import get_exporter, list_exporters
from ..quality import data_quality_report, flag_anomalies, invalidate_result
from ..quantization import compare_quantizations
from ..validate import load_result
from .common import echo_json, fail, load_results_dir


def cmd_export(args: argparse.Namespace) -> int:
    """Generate dataset views (JSON/CSV/Markdown) from published results."""
    results_dir = Path(args.results_dir)
    if not results_dir.is_dir():
        fail(f"{results_dir} is not a directory")
        return EXIT_USAGE_ERROR
    try:
        outputs = export_dataset(results_dir, Path(args.output), strict=args.strict)
    except DatasetLoadError as exc:
        fail(str(exc))
        return EXIT_VALIDATION_ERROR
    for p in outputs:
        print(f"Written: {p}")
    if getattr(args, "parquet", False):
        pq_path = Path(args.output) / "dataset.parquet"
        try:
            written = export_parquet(results_dir, pq_path)
        except Exception as exc:  # noqa: BLE001 - surfaced as a CLI failure
            fail(f"parquet export failed: {exc}")
            return EXIT_VALIDATION_ERROR
        print(f"Written: {written}")
    return EXIT_OK


def cmd_exporters(_args: argparse.Namespace) -> int:
    for name in list_exporters():
        print(name)
    return EXIT_OK


def cmd_export_as(args: argparse.Namespace) -> int:
    """Export results via a named exporter (#47)."""
    results = load_results_dir(Path(args.results_dir))
    if not results:
        fail(f"no result JSON files found in {args.results_dir}")
        return EXIT_USAGE_ERROR
    try:
        exporter = get_exporter(args.format)
    except KeyError as exc:
        fail(str(exc))
        return EXIT_USAGE_ERROR
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    written = exporter.export(results, out_path)
    print(f"Exported {len(results)} result(s) to: {written}")
    return EXIT_OK


def cmd_evaluate(args: argparse.Namespace) -> int:
    """Run a quality evaluator over a JSONL responses file (#16)."""
    try:
        dataset = load_dataset(Path(args.dataset))
    except (OSError, ValueError) as exc:
        fail(str(exc))
        return EXIT_USAGE_ERROR
    responses = [str(item.get("response", "")) for item in dataset]
    expected = [item.get("expected") for item in dataset]
    try:
        report = run_evaluation(args.evaluator, responses, expected)
    except KeyError as exc:
        fail(str(exc))
        return EXIT_USAGE_ERROR
    echo_json(report)
    return EXIT_OK


def cmd_evaluators(_args: argparse.Namespace) -> int:
    for name in list_evaluators():
        print(name)
    return EXIT_OK


def cmd_quantization(args: argparse.Namespace) -> int:
    """Compare quantization variants from published results (#19)."""
    results = load_results_dir(Path(args.results_dir))
    if not results:
        fail(f"no result JSON files found in {args.results_dir}")
        return EXIT_USAGE_ERROR
    echo_json(compare_quantizations(results))
    return EXIT_OK


def cmd_quality(args: argparse.Namespace) -> int:
    """Data-quality checks for one result or a whole directory (#43)."""
    path = Path(args.path)
    if path.is_dir():
        reports = {}
        for p in sorted(path.glob("*.json")):
            try:
                reports[p.name] = data_quality_report(json.loads(p.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
        echo_json(reports)
        return EXIT_OK
    try:
        result = load_result(path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        fail(str(exc))
        return EXIT_VALIDATION_ERROR
    echo_json(data_quality_report(result))
    return EXIT_OK


def cmd_invalidate(args: argparse.Namespace) -> int:
    """Record an invalidation; original history is preserved (#42)."""
    try:
        result = load_result(Path(args.result))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        fail(str(exc))
        return EXIT_VALIDATION_ERROR
    record = invalidate_result(result, args.reason, args.replacement)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(f"Invalidation record written: {out_path}")
    return EXIT_OK


def cmd_anomalies(args: argparse.Namespace) -> int:
    """Flag statistically suspicious results for review (#44)."""
    results = load_results_dir(Path(args.results_dir))
    if not results:
        fail(f"no result JSON files found in {args.results_dir}")
        return EXIT_USAGE_ERROR
    flags = flag_anomalies(results, metric=args.metric, z_threshold=args.z)
    echo_json(
        {
            "metric": args.metric,
            "z_threshold": args.z,
            "results_scanned": len(results),
            "flags": flags,
        }
    )
    return EXIT_OK


def cmd_snapshot(args: argparse.Namespace) -> int:
    """Build a versioned dataset snapshot manifest (#41)."""
    results_dir = Path(args.results_dir)
    if not results_dir.is_dir():
        fail(f"{results_dir} is not a directory")
        return EXIT_USAGE_ERROR
    previous = None
    prev_path = Path(args.previous) if args.previous else None
    if prev_path and prev_path.is_file():
        previous = json.loads(prev_path.read_text(encoding="utf-8"))
    try:
        manifest = build_snapshot_manifest(results_dir, args.version, previous)
    except ValueError as exc:
        fail(str(exc))
        return EXIT_VALIDATION_ERROR
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Snapshot manifest written: {out_path}")
    return EXIT_OK


def register(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    exp = sub.add_parser("export", help="Generate dataset views from published results")
    exp.add_argument("results_dir", nargs="?", default="results/published")
    exp.add_argument("--output", default="results/dataset")
    exp.add_argument(
        "--strict",
        action="store_true",
        help="Fail closed on unreadable/schema-invalid results (default for publishing)",
    )
    exp.add_argument(
        "--parquet",
        action="store_true",
        help="Also emit a Parquet copy of the dataset (requires the 'parquet' extra)",
    )
    exp.set_defaults(func=cmd_export)

    sub.add_parser("evaluators", help="List registered evaluators").set_defaults(
        func=cmd_evaluators
    )

    ev = sub.add_parser("evaluate", help="Run a quality evaluator over a JSONL dataset")
    ev.add_argument("--evaluator", required=True)
    ev.add_argument("--dataset", required=True, help="JSONL with input/expected/response")
    ev.set_defaults(func=cmd_evaluate)

    quant = sub.add_parser("quantization", help="Compare quantization variants")
    quant.add_argument("--results-dir", default="results/published")
    quant.set_defaults(func=cmd_quantization)

    qual = sub.add_parser("quality", help="Data-quality checks (file or directory)")
    qual.add_argument("path")
    qual.set_defaults(func=cmd_quality)

    inval = sub.add_parser("invalidate", help="Record an invalidation (history preserved)")
    inval.add_argument("result")
    inval.add_argument("--reason", required=True)
    inval.add_argument("--replacement", default=None, help="Replacement run id")
    inval.add_argument("--output", default="results/invalidations/invalidation.json")
    inval.set_defaults(func=cmd_invalidate)

    anom = sub.add_parser("anomalies", help="Flag suspicious results for review")
    anom.add_argument("--results-dir", default="results/published")
    anom.add_argument("--metric", default="generation_tokens_per_second")
    anom.add_argument("--z", type=float, default=3.0)
    anom.set_defaults(func=cmd_anomalies)

    snap = sub.add_parser("snapshot", help="Versioned dataset snapshot manifest")
    snap.add_argument("--version", required=True)
    snap.add_argument("--results-dir", default="results/published")
    snap.add_argument("--previous", default=None, help="Previous manifest JSON")
    snap.add_argument("--output", default="results/snapshots/snapshot.json")
    snap.set_defaults(func=cmd_snapshot)

    sub.add_parser("exporters", help="List registered exporters").set_defaults(func=cmd_exporters)

    exp2 = sub.add_parser("export-as", help="Export results with a named exporter")
    exp2.add_argument("--format", required=True, help="json, csv, markdown, sqlite, ...")
    exp2.add_argument("--results-dir", default="results/published")
    exp2.add_argument("--output", required=True)
    exp2.set_defaults(func=cmd_export_as)
