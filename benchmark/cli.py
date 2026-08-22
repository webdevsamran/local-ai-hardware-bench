"""aihwbench command-line interface.

Subcommands:
  system-info   Print detected hardware
  detect        Print full system + runtime detection (JSON)
  runtimes      List runtime backends and their status
  benchmark     Run a real benchmark and save a result document
  validate      Validate a result JSON file against the schema
  report        Render a human-readable report from a result file
  compare       Compare two result files
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .backends import BACKENDS, BackendError, BenchmarkConfig, detect_all, resolve
from .compare import compare_results, render_comparison
from .report import render_report
from .runner import run_benchmark, save_result
from .system_info import detect_system
from .validate import load_result, validate_file


def _print_json(data: object) -> None:
    print(json.dumps(data, indent=2))


def cmd_system_info(_args: argparse.Namespace) -> int:
    _print_json(detect_system())
    return 0


def cmd_detect(_args: argparse.Namespace) -> int:
    _print_json({"system": detect_system(), "runtimes": detect_all()})
    return 0


def cmd_runtimes(_args: argparse.Namespace) -> int:
    for info in detect_all():
        status = info["status"]
        version = info.get("version") or "-"
        print(f"{info['name']:<14} {status:<24} {version}")
        if info.get("detail"):
            print(f"{'':<14} {info['detail']}")
    return 0


def cmd_benchmark(args: argparse.Namespace) -> int:
    if args.runtime == "ollama" and not args.model:
        print("ERROR: --model is required for the ollama runtime", file=sys.stderr)
        return 2
    if args.runtime in ("llama.cpp", "onnxruntime", "openvino") and not args.model_path:
        print(f"ERROR: --model-path is required for the {args.runtime} runtime",
              file=sys.stderr)
        return 2
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
        return 2

    out_dir = Path(args.output)
    raw_path = save_result(result, out_dir / "raw")
    report_path = out_dir / f"{result['run_id']}.md"
    report_path.write_text(render_report(result), encoding="utf-8")
    print(f"Result saved to: {raw_path}")
    print(f"Report saved to: {report_path}")
    print()
    print(render_report(result))
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    valid, errors = validate_file(Path(args.result))
    if valid:
        print(f"VALID: {args.result}")
        return 0
    print(f"INVALID: {args.result}", file=sys.stderr)
    for error in errors:
        print(f"  - {error}", file=sys.stderr)
    return 1


def cmd_report(args: argparse.Namespace) -> int:
    result = load_result(Path(args.result))
    print(render_report(result))
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    a = load_result(Path(args.result_a))
    b = load_result(Path(args.result_b))
    comparison = compare_results(a, b)
    print(render_comparison(comparison))
    if args.json:
        _print_json(comparison)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aihwbench",
        description="Open Local AI Hardware Benchmark - vendor-neutral local AI runtime benchmarking",
    )
    parser.add_argument("--version", action="version", version=f"aihwbench {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("system-info", help="Print detected hardware").set_defaults(func=cmd_system_info)
    sub.add_parser("detect", help="Full system + runtime detection as JSON").set_defaults(func=cmd_detect)
    sub.add_parser("runtimes", help="List runtime backends and status").set_defaults(func=cmd_runtimes)

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
    rep.set_defaults(func=cmd_report)

    cmp_ = sub.add_parser("compare", help="Compare two result files")
    cmp_.add_argument("result_a")
    cmp_.add_argument("result_b")
    cmp_.add_argument("--json", action="store_true", help="Also print structured JSON")
    cmp_.set_defaults(func=cmd_compare)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
