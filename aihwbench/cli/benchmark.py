"""Benchmark execution commands: single runs, suites, sweeps, manifests,
capacity ladders and auto-tuning."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from ..analysis.tune import run_tuner
from ..backends import BACKENDS, BackendError, BenchmarkConfig, resolve
from ..capacity import CapacityConfig, run_capacity_ladder
from ..exit_codes import EXIT_OK, EXIT_USAGE_ERROR
from ..manifests import ExperimentError, load_experiment
from ..report import render_report
from ..runner import run_benchmark, save_result
from ..suites import list_suites, load_suite, run_suite
from ..sweep import SweepSpec, matrix_to_csv_rows, run_sweep
from .common import echo_json, fail


def cmd_benchmark(args: argparse.Namespace) -> int:
    if args.runtime == "ollama" and not args.model:
        fail("--model is required for the ollama runtime")
        return EXIT_USAGE_ERROR
    if args.runtime in ("llama.cpp", "onnxruntime", "openvino") and not args.model_path:
        fail(f"--model-path is required for the {args.runtime} runtime")
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
        fail(str(exc))
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


def cmd_suite(args: argparse.Namespace) -> int:
    """Run a versioned benchmark suite profile."""
    if args.list:
        for name in list_suites():
            print(name)
        return EXIT_OK
    try:
        suite = load_suite(args.name)
    except FileNotFoundError as exc:
        fail(str(exc))
        return EXIT_USAGE_ERROR
    workload = suite["workload"]
    print(f"Suite: {suite['name']} - {suite['description']}")
    print(f"Workload: max_tokens={workload['max_tokens']} iterations={workload['iterations']}")
    paths = run_suite(args.name, args.runtime, args.model_path or args.model, Path(args.output))
    for p in paths:
        print(f"Result saved to: {p}")
    return EXIT_OK


def cmd_sweep(args: argparse.Namespace) -> int:
    """Run a parameter sweep over one runtime/model (#5)."""
    axes: dict[str, tuple] = {}
    if args.max_tokens_list:
        axes["max_tokens"] = tuple(int(v) for v in args.max_tokens_list.split(","))
    if args.iterations_list:
        axes["iterations"] = tuple(int(v) for v in args.iterations_list.split(","))
    if args.context_list:
        axes["context_length"] = tuple(int(v) for v in args.context_list.split(","))
    if args.device_list:
        axes["device"] = tuple(args.device_list.split(","))
    if not axes:
        fail(
            "provide at least one sweep axis "
            "(--max-tokens-list/--iterations-list/--context-list/--device-list)"
        )
        return EXIT_USAGE_ERROR
    spec = SweepSpec(axes=axes, base={"runtime": args.runtime, "model": args.model or ""})

    def run_fn(point: dict) -> dict:
        config = BenchmarkConfig(
            model=point.get("model", ""),
            max_tokens=point.get("max_tokens", 128),
            iterations=point.get("iterations", 5),
            context_length=point.get("context_length", 2048),
            device=point.get("device", "auto"),
            extra={"model_path": args.model_path},
        )
        return run_benchmark(point["runtime"], config)

    matrix = run_sweep(spec, run_fn)
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"sweep-{args.runtime}.json"
    out_path.write_text(
        json.dumps({"axes": {k: list(v) for k, v in axes.items()}, "matrix": matrix}, indent=2),
        encoding="utf-8",
    )
    csv_rows = matrix_to_csv_rows(matrix)
    csv_path = out_dir / f"sweep-{args.runtime}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(csv_rows[0].keys()))
        writer.writeheader()
        writer.writerows(csv_rows)
    print(f"Sweep matrix saved to: {out_path}")
    print(f"CSV saved to: {csv_path}")
    for row in matrix:
        params = ", ".join(f"{k}={v}" for k, v in sorted(row["params"].items()))
        m = row["metrics"]
        tok = m.get("generation_tokens_per_second")
        print(
            f"  {params:<50} tok/s={tok if tok is not None else '-'}"
            + (f" error={row['error']}" if row["error"] else "")
        )
    return EXIT_OK


def cmd_run_manifest(args: argparse.Namespace) -> int:
    """Execute a declarative experiment manifest (#6)."""
    try:
        experiment = load_experiment(Path(args.manifest))
    except (OSError, ExperimentError, json.JSONDecodeError) as exc:
        fail(str(exc))
        return EXIT_USAGE_ERROR
    print(f"Experiment: {experiment.name}")
    print(f"  runtimes={list(experiment.runtimes)} models={list(experiment.models)}")
    print(f"  workloads={list(experiment.workloads)} repetitions={experiment.repetitions}")
    out_dir = Path(args.output)
    paths: list[Path] = []
    try:
        for runtime in experiment.runtimes:
            for model in experiment.models or ("",):
                for rep in range(experiment.repetitions):
                    config = BenchmarkConfig(
                        model=model,
                        iterations=args.iterations,
                        device="auto",
                        extra={"model_path": args.model_path},
                    )
                    result = run_benchmark(runtime, config)
                    raw_path = save_result(result, out_dir / "raw")
                    paths.append(raw_path)
                    print(f"  [{runtime}/{model or '-'} rep {rep + 1}] -> {raw_path.name}")
    except BackendError as exc:
        fail(str(exc))
        return EXIT_USAGE_ERROR
    print(f"{len(paths)} result(s) written under {out_dir / 'raw'}")
    return EXIT_OK


def cmd_capacity(args: argparse.Namespace) -> int:
    """Concurrency ladder capacity test (#8)."""
    levels = tuple(int(v) for v in args.levels.split(","))
    config = CapacityConfig(
        concurrency_levels=levels,
        requests_per_level=args.requests_per_level,
        sustainability_factor=args.sustainability_factor,
    )

    def execute(_request_id: int) -> dict:
        bench_config = BenchmarkConfig(
            model=args.model or "",
            max_tokens=args.max_tokens,
            warmup_runs=0,
            iterations=1,
            device=args.device,
            extra={"model_path": args.model_path},
        )
        result = run_benchmark(args.runtime, bench_config)
        metrics = result.get("metrics", {})
        return {
            "completion_tokens": metrics.get("generation_tokens_per_second"),
            "ttft_ms": metrics.get("ttft_ms"),
        }

    try:
        resolve(args.runtime)
        report = run_capacity_ladder(config, execute)
    except BackendError as exc:
        fail(str(exc))
        return EXIT_USAGE_ERROR
    echo_json(report.as_dict())
    return EXIT_OK


def cmd_tune(args: argparse.Namespace) -> int:
    """Auto-tune a safe configuration space (#50)."""
    axes: dict[str, tuple] = {}
    if args.threads_list:
        axes["threads"] = tuple(int(v) for v in args.threads_list.split(","))
    if args.batch_list:
        axes["batch_size"] = tuple(int(v) for v in args.batch_list.split(","))
    if args.context_list:
        axes["context_length"] = tuple(int(v) for v in args.context_list.split(","))
    if args.gpu_layers_list:
        axes["gpu_layers"] = tuple(int(v) for v in args.gpu_layers_list.split(","))
    if args.concurrency_list:
        axes["concurrency"] = tuple(int(v) for v in args.concurrency_list.split(","))

    def run_fn(point: dict) -> dict:
        config = BenchmarkConfig(
            model=args.model or "",
            max_tokens=args.max_tokens,
            iterations=args.iterations,
            context_length=point.get("context_length", 2048),
            device=args.device,
            extra={"model_path": args.model_path, **point},
        )
        return run_benchmark(args.runtime, config)

    try:
        resolve(args.runtime)
        report = run_tuner(axes, run_fn)
    except BackendError as exc:
        fail(str(exc))
        return EXIT_USAGE_ERROR
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"tune-{args.runtime}.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Tuning report saved to: {out_path}")
    echo_json({k: v for k, v in report.items() if k != "balanced_frontier"})
    return EXIT_OK


def register(sub: argparse._SubParsersAction) -> None:
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

    sweep_p = sub.add_parser("sweep", help="Parameter sweep producing a structured matrix")
    sweep_p.add_argument("--runtime", required=True, choices=sorted(BACKENDS))
    sweep_p.add_argument("--model", default=None)
    sweep_p.add_argument("--model-path", default=None)
    sweep_p.add_argument("--max-tokens-list", default=None, help="Comma-separated values")
    sweep_p.add_argument("--iterations-list", default=None, help="Comma-separated values")
    sweep_p.add_argument("--context-list", default=None, help="Comma-separated values")
    sweep_p.add_argument("--device-list", default=None, help="Comma-separated values")
    sweep_p.add_argument("--output", default="results/sweeps")
    sweep_p.set_defaults(func=cmd_sweep)

    run_p = sub.add_parser("run", help="Run a declarative experiment manifest (JSON/TOML/YAML)")
    run_p.add_argument("manifest")
    run_p.add_argument("--iterations", type=int, default=5)
    run_p.add_argument("--model-path", default=None)
    run_p.add_argument("--output", default="results/experiments")
    run_p.set_defaults(func=cmd_run_manifest)

    cap = sub.add_parser("capacity", help="Concurrency ladder capacity test")
    cap.add_argument("--runtime", required=True, choices=sorted(BACKENDS))
    cap.add_argument("--model", default=None)
    cap.add_argument("--model-path", default=None)
    cap.add_argument("--levels", default="1,2,4,8", help="Comma-separated concurrency levels")
    cap.add_argument("--requests-per-level", type=int, default=20)
    cap.add_argument("--max-tokens", type=int, default=64)
    cap.add_argument("--device", default="auto")
    cap.add_argument("--sustainability-factor", type=float, default=2.0)
    cap.set_defaults(func=cmd_capacity)

    tune_p = sub.add_parser("tune", help="Auto-tune a safe configuration space")
    tune_p.add_argument("--runtime", required=True, choices=sorted(BACKENDS))
    tune_p.add_argument("--model", default=None)
    tune_p.add_argument("--model-path", default=None)
    tune_p.add_argument("--threads-list", default=None)
    tune_p.add_argument("--batch-list", default=None)
    tune_p.add_argument("--context-list", default=None)
    tune_p.add_argument("--gpu-layers-list", default=None)
    tune_p.add_argument("--concurrency-list", default=None)
    tune_p.add_argument("--max-tokens", type=int, default=64)
    tune_p.add_argument("--iterations", type=int, default=3)
    tune_p.add_argument("--device", default="auto")
    tune_p.add_argument("--output", default="results/tuning")
    tune_p.set_defaults(func=cmd_tune)
