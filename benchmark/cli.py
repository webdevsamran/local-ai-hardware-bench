"""aihwbench command-line interface."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .analysis import (
    analyze_bottlenecks,
    estimate_model_fit,
    recommend_configuration,
)
from .analysis.tune import run_tuner
from .backends import (
    BACKENDS,
    BackendError,
    BenchmarkConfig,
    detect_all,
    resolve,
)
from .capacity import CapacityConfig, run_capacity_ladder
from .compare import NOT_COMPARABLE, compare_results, render_comparison
from .evaluators import list_evaluators, load_dataset, run_evaluation
from .exit_codes import (
    EXIT_CONFIGURATION_ERROR,
    EXIT_NOT_COMPARABLE,
    EXIT_OK,
    EXIT_REGRESSION_DETECTED,
    EXIT_USAGE_ERROR,
    EXIT_VALIDATION_ERROR,
)
from .export import export_dataset
from .manifests import ExperimentError, load_experiment
from .quantization import compare_quantizations
from .regression import RegressionThresholds, evaluate_regression
from .report import render_report
from .runner import run_benchmark, save_result
from .suites import list_suites, load_suite, run_suite
from .sweep import SweepSpec, matrix_to_csv_rows, run_sweep
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


def cmd_baseline(args: argparse.Namespace) -> int:
    """Save a result as a named baseline for regression checks."""
    try:
        result = load_result(Path(args.result))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_VALIDATION_ERROR
    baselines_dir = Path(args.baselines_dir)
    baselines_dir.mkdir(parents=True, exist_ok=True)
    path = baselines_dir / f"{args.name}.json"
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"Baseline saved: {path}")
    return EXIT_OK


def cmd_regression(args: argparse.Namespace) -> int:
    """Compare a candidate result against a saved baseline."""
    baseline_path = Path(args.baselines_dir) / f"{args.baseline}.json"
    if not baseline_path.is_file():
        print(
            f"ERROR: baseline {args.baseline!r} not found at {baseline_path}",
            file=sys.stderr,
        )
        return EXIT_USAGE_ERROR
    try:
        baseline = load_result(baseline_path)
        candidate = load_result(Path(args.candidate))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_VALIDATION_ERROR
    thresholds = RegressionThresholds(
        throughput_max_regression_pct=args.throughput_pct,
        ttft_max_increase_ms=args.ttft_ms,
        ttft_max_increase_pct=args.ttft_pct,
        latency_p95_max_regression_pct=args.latency_pct,
        memory_max_increase_mb=args.memory_mb,
        memory_max_increase_pct=args.memory_pct,
        power_max_increase_watts=args.power_w,
        power_max_increase_pct=args.power_pct,
    )
    report = evaluate_regression(baseline, candidate, thresholds)
    if args.json:
        _json(report.to_dict())
    else:
        print(f"Classification: {report.classification}")
        print(f"Status: {report.status}")
        for c in report.checks:
            print(
                f"  {c.status:<8} {c.metric:<32} "
                f"base={c.baseline} cand={c.candidate} "
                f"delta={c.delta} ({c.delta_pct}%)"
            )
            if c.reason:
                print(f"           {c.reason}")
    if report.status == "FAIL":
        return EXIT_REGRESSION_DETECTED
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
        print(
            "ERROR: provide at least one sweep axis "
            "(--max-tokens-list/--iterations-list/--context-list/--device-list)",
            file=sys.stderr,
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
    import csv as _csv

    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        writer = _csv.DictWriter(fh, fieldnames=list(csv_rows[0].keys()))
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
        print(f"ERROR: {exc}", file=sys.stderr)
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
        print(f"ERROR: {exc}", file=sys.stderr)
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
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_USAGE_ERROR
    _json(report.as_dict())
    return EXIT_OK


def _load_results_dir(results_dir: Path) -> list[dict]:
    results = []
    for path in sorted(results_dir.glob("*.json")):
        try:
            results.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    return results


def cmd_analyze(args: argparse.Namespace) -> int:
    """Bottleneck analysis from a result's measured telemetry (#22)."""
    try:
        result = load_result(Path(args.result))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_VALIDATION_ERROR
    findings = analyze_bottlenecks(result.get("metrics", {}), result.get("system", {}))
    _json({"run_id": result.get("run_id"), "findings": findings})
    return EXIT_OK


def cmd_fit(args: argparse.Namespace) -> int:
    """Estimate whether a model fits in available memory (#20)."""
    system = detect_system()
    ram_gb = system.get("ram_gb")
    report = estimate_model_fit(
        parameters_text=args.parameters,
        quantization=args.quantization,
        available_vram_mb=system.get("gpu_vram_mb"),
        available_ram_mb=ram_gb * 1000.0 if isinstance(ram_gb, (int, float)) else None,
        context_tokens=args.context_tokens,
    )
    _json(report)
    return EXIT_OK


def cmd_recommend(args: argparse.Namespace) -> int:
    """Recommend a configuration for this hardware (#21)."""
    system = detect_system()
    measured = _load_results_dir(Path(args.results_dir)) if args.results_dir else []
    _json(recommend_configuration(system, measured))
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
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_USAGE_ERROR
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"tune-{args.runtime}.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Tuning report saved to: {out_path}")
    _json({k: v for k, v in report.items() if k != "balanced_frontier"})
    return EXIT_OK


def cmd_evaluate(args: argparse.Namespace) -> int:
    """Run a quality evaluator over a JSONL responses file (#16)."""
    try:
        dataset = load_dataset(Path(args.dataset))
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_USAGE_ERROR
    responses = [str(item.get("response", "")) for item in dataset]
    expected = [item.get("expected") for item in dataset]
    try:
        report = run_evaluation(args.evaluator, responses, expected)
    except KeyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_USAGE_ERROR
    _json(report)
    return EXIT_OK


def cmd_evaluators(_args: argparse.Namespace) -> int:
    for name in list_evaluators():
        print(name)
    return EXIT_OK


def cmd_quantization(args: argparse.Namespace) -> int:
    """Compare quantization variants from published results (#19)."""
    results = _load_results_dir(Path(args.results_dir))
    if not results:
        print(f"ERROR: no result JSON files found in {args.results_dir}", file=sys.stderr)
        return EXIT_USAGE_ERROR
    _json(compare_quantizations(results))
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

    base_p = sub.add_parser("baseline", help="Save a result as a named baseline")
    base_p.add_argument("result")
    base_p.add_argument("--name", required=True)
    base_p.add_argument("--baselines-dir", default="results/baselines")
    base_p.set_defaults(func=cmd_baseline)

    reg = sub.add_parser("regression", help="Check candidate vs baseline")
    reg.add_argument("--baseline", required=True)
    reg.add_argument("candidate")
    reg.add_argument("--baselines-dir", default="results/baselines")
    reg.add_argument("--throughput-pct", type=float, default=10.0)
    reg.add_argument("--ttft-ms", type=float, default=250.0)
    reg.add_argument("--ttft-pct", type=float, default=50.0)
    reg.add_argument("--latency-pct", type=float, default=25.0)
    reg.add_argument("--memory-mb", type=float, default=1024.0)
    reg.add_argument("--memory-pct", type=float, default=50.0)
    reg.add_argument("--power-w", type=float, default=15.0)
    reg.add_argument("--power-pct", type=float, default=50.0)
    reg.add_argument("--json", action="store_true")
    reg.set_defaults(func=cmd_regression)

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

    ana = sub.add_parser("analyze", help="Bottleneck analysis from measured telemetry")
    ana.add_argument("result")
    ana.set_defaults(func=cmd_analyze)

    fit_p = sub.add_parser("fit", help="Estimate model memory fit (labeled estimate)")
    fit_p.add_argument("--parameters", required=True, help="e.g. 7B, 1.5b, 350M")
    fit_p.add_argument("--quantization", required=True, help="e.g. q4_k_m, fp16")
    fit_p.add_argument("--context-tokens", type=int, default=4096)
    fit_p.set_defaults(func=cmd_fit)

    rec = sub.add_parser("recommend", help="Recommend a configuration for this hardware")
    rec.add_argument("--results-dir", default=None, help="Prior results to anchor on")
    rec.set_defaults(func=cmd_recommend)

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

    ev = sub.add_parser("evaluate", help="Run a quality evaluator over a JSONL dataset")
    ev.add_argument("--evaluator", required=True)
    ev.add_argument("--dataset", required=True, help="JSONL with input/expected/response")
    ev.set_defaults(func=cmd_evaluate)

    sub.add_parser("evaluators", help="List registered evaluators").set_defaults(
        func=cmd_evaluators
    )

    quant = sub.add_parser("quantization", help="Compare quantization variants")
    quant.add_argument("--results-dir", default="results/published")
    quant.set_defaults(func=cmd_quantization)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
