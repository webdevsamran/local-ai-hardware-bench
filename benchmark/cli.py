"""aihwbench command-line interface."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .backends import (
    BACKENDS,
    BackendError,
    BenchmarkConfig,
    detect_all,
    resolve,
)
from .compare import NOT_COMPARABLE, compare_results, render_comparison
from .exit_codes import (
    EXIT_CONFIGURATION_ERROR,
    EXIT_NOT_COMPARABLE,
    EXIT_OK,
    EXIT_USAGE_ERROR,
    EXIT_VALIDATION_ERROR,
)
from .export import export_dataset
from .report import render_report
from .runner import run_benchmark, save_result
from .suites import list_suites, load_suite, run_suite
from .system_info import detect_system
from .validate import load_result, validate_file


def _json(data: object) -> None:
    print(json.dumps(data, indent=2, default=str))


def cmd_system_info(_args: argparse.Namespace) -> int:
    _json(detect_system())
    return EXIT_OK


def cmd_detect(_args: argparse.Namespace) -> int:
    _json({"system": detect_system(), "runtimes": detect_all()})
    return EXIT_OK


def cmd_doctor(_args: argparse.Namespace) -> int:
    """Actionable hardware/runtime preconditions report."""
    system = detect_system()
    problems: list[str] = []
    if not system.get("cpu"):
        problems.append("CPU detection failed")
    if not system.get("gpu"):
        problems.append("No GPU detected")
    print("== System ==")
    for key, value in system.items():
        print(f"  {key}: {value}")
    print()
    print("== Runtimes ==")
    for info in detect_all():
        status = info["status"]
        print(f"  {info['name']:<14} {status:<24} {info.get('version') or '-'}")
        if info.get("detail"):
            print(f"  {'':<14} {info['detail']}")
    print()
    if problems:
        print("Recommendations:")
        for p in problems:
            print(f"  - {p}")
        return EXIT_CONFIGURATION_ERROR
    return EXIT_OK


def cmd_runtimes(_args: argparse.Namespace) -> int:
    for info in detect_all():
        status = info["status"]
        version = info.get("version") or "-"
        print(f"{info['name']:<14} {status:<24} {version}")
        if info.get("detail"):
            print(f"{'':<14} {info['detail']}")
    return EXIT_OK


def cmd_benchmark(args: argparse.Namespace) -> int:
    if args.runtime == "ollama" and not args.model:
        print("ERROR: --model is required for the ollama runtime", file=sys.stderr)
        return EXIT_USAGE_ERROR
    if args.runtime in ("llama.cpp", "onnxruntime", "openvino") and not args.model_path:
        print(f"ERROR: --model-path is required for the {args.runtime} runtime", file=sys.stderr)
        return EXIT_USAGE_ERROR
    config = BenchmarkConfig(
        model=args.model or "",
        max_tokens=args.max_tokens,
        warmup_runs=args.warmup,
        iterations=args.iterations,
        temperature=args.temperature,
        seed=args.seed,
        context_length=args.context_length,
        device=args.device,
        extra={"model_path": args.model_path},
    )
    try:
        resolve(args.runtime)
        result = run_benchmark(args.runtime, config)
    except BackendError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_USAGE_ERROR

    out_dir = Path(args.output)
    raw_path = save_result(result, out_dir / "raw")
    report_path = out_dir / f"{result['run_id']}.md"
    report_path.write_text(render_report(result), encoding="utf-8")
    print(f"Result saved to: {raw_path}")
    print(f"Report saved to: {report_path}")
    print()
    print(render_report(result))
    return EXIT_OK


def cmd_validate(args: argparse.Namespace) -> int:
    valid, errors = validate_file(Path(args.result))
    if valid:
        print(f"VALID: {args.result}")
        return EXIT_OK
    print(f"INVALID: {args.result}", file=sys.stderr)
    for error in errors:
        print(f"  - {error}", file=sys.stderr)
    return EXIT_VALIDATION_ERROR


def cmd_report(args: argparse.Namespace) -> int:
    try:
        result = load_result(Path(args.result))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_VALIDATION_ERROR
    if args.output:
        Path(args.output).write_text(render_report(result), encoding="utf-8")
    else:
        print(render_report(result))
    return EXIT_OK


def cmd_compare(args: argparse.Namespace) -> int:
    try:
        a = load_result(Path(args.result_a))
        b = load_result(Path(args.result_b))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_VALIDATION_ERROR
    comparison = compare_results(a, b, force=args.force)
    print(render_comparison(comparison))
    if args.json:
        _json(comparison)
    if comparison["classification"] == NOT_COMPARABLE and not args.force:
        return EXIT_NOT_COMPARABLE
    return EXIT_OK


def cmd_suite(args: argparse.Namespace) -> int:
    """Run a versioned benchmark suite profile."""
    if args.list:
        for name in list_suites():
            print(name)
        return EXIT_OK
    try:
        suite = load_suite(args.name)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_USAGE_ERROR
    workload = suite["workload"]
    print(f"Suite: {suite['name']} - {suite['description']}")
    print(f"Workload: max_tokens={workload['max_tokens']} iterations={workload['iterations']}")
    paths = run_suite(args.name, args.runtime, args.model_path or args.model, Path(args.output))
    for p in paths:
        print(f"Result saved to: {p}")
    return EXIT_OK


def cmd_export(args: argparse.Namespace) -> int:
    """Generate dataset views (JSON/CSV/Markdown) from published results."""
    results_dir = Path(args.results_dir)
    if not results_dir.is_dir():
        print(f"ERROR: {results_dir} is not a directory", file=sys.stderr)
        return EXIT_USAGE_ERROR
    outputs = export_dataset(results_dir, Path(args.output))
    for p in outputs:
        print(f"Written: {p}")
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aihwbench",
        description="AIHWBench - vendor-neutral local AI runtime benchmarking",
    )
    parser.add_argument("--version", action="version", version=f"aihwbench {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("system-info", help="Print detected hardware").set_defaults(func=cmd_system_info)
    sub.add_parser("detect", help="Full system + runtime detection as JSON").set_defaults(
        func=cmd_detect
    )
    sub.add_parser("doctor", help="Diagnose hardware/runtime preconditions").set_defaults(
        func=cmd_doctor
    )
    sub.add_parser("runtimes", help="List runtime backends and status").set_defaults(
        func=cmd_runtimes
    )

    bench = sub.add_parser("benchmark", help="Run a real benchmark")
    bench.add_argument("--runtime", required=True, choices=sorted(BACKENDS))
    bench.add_argument("--model", default=None, help="Model identifier (e.g. ollama tag)")
    bench.add_argument("--model-path", default=None, help="Local model file path (llama.cpp)")
    bench.add_argument("--max-tokens", type=int, default=128)
    bench.add_argument("--warmup", type=int, default=2)
    bench.add_argument("--iterations", type=int, default=5)
    bench.add_argument("--temperature", type=float, default=0.0)
    bench.add_argument("--seed", type=int, default=42)
    bench.add_argument("--context-length", type=int, default=2048)
    bench.add_argument("--device", default="auto", help="auto | cpu | cuda | gpu | npu")
    bench.add_argument("--output", default="results", help="Results output directory")
    bench.set_defaults(func=cmd_benchmark)

    val = sub.add_parser("validate", help="Validate a result JSON file")
    val.add_argument("result")
    val.set_defaults(func=cmd_validate)

    rep = sub.add_parser("report", help="Render a markdown report")
    rep.add_argument("result")
    rep.add_argument("--output", default=None, help="Write report to file")
    rep.set_defaults(func=cmd_report)

    cmp_ = sub.add_parser("compare", help="Compare two result files")
    cmp_.add_argument("result_a")
    cmp_.add_argument("result_b")
    cmp_.add_argument("--json", action="store_true", help="Also print structured JSON")
    cmp_.add_argument("--force", action="store_true", help="Compare even when NOT_COMPARABLE")
    cmp_.set_defaults(func=cmd_compare)

    suite_p = sub.add_parser("suite", help="Run a versioned benchmark suite profile")
    suite_p.add_argument("name", nargs="?", default=None, help="Suite name (e.g. smoke)")
    suite_p.add_argument("--list", action="store_true", help="List available suites")
    suite_p.add_argument("--runtime", default="ollama")
    suite_p.add_argument("--model", default=None, help="Model identifier (ollama tag)")
    suite_p.add_argument(
        "--model-path", default=None, help="Local model file path (llama.cpp/ONNX/OpenVINO)"
    )
    suite_p.add_argument("--output", default="results")
    suite_p.set_defaults(func=cmd_suite)

    exp = sub.add_parser("export", help="Generate dataset views from published results")
    exp.add_argument("results_dir", nargs="?", default="results/published")
    exp.add_argument("--output", default="results/dataset")
    exp.set_defaults(func=cmd_export)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
