"""Result inspection commands: validate, report, compare, baselines,
regression gates and hardware-fit analysis."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from ..analysis import analyze_bottlenecks, estimate_model_fit, recommend_configuration
from ..comparability import NOT_COMPARABLE
from ..compare import compare_results, render_comparison
from ..exit_codes import (
    EXIT_NOT_COMPARABLE,
    EXIT_OK,
    EXIT_REGRESSION_DETECTED,
    EXIT_USAGE_ERROR,
    EXIT_VALIDATION_ERROR,
)
from ..regression import RegressionThresholds, evaluate_regression
from ..report import render_report
from ..score import compute_score
from ..system_info import detect_system
from ..validate import load_result, validate_file
from .common import echo_json, fail, load_results_dir


def cmd_validate(args: argparse.Namespace) -> int:
    valid, errors = validate_file(Path(args.result))
    if valid:
        print(f"VALID: {args.result}")
        return EXIT_OK
    fail(f"INVALID: {args.result}")
    for error in errors:
        print(f"  - {error}", file=sys.stderr)
    return EXIT_VALIDATION_ERROR


def cmd_report(args: argparse.Namespace) -> int:
    try:
        result = load_result(Path(args.result))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        fail(str(exc))
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
        fail(str(exc))
        return EXIT_VALIDATION_ERROR
    comparison = compare_results(a, b, force=args.force)
    print(render_comparison(comparison))
    if args.json:
        echo_json(comparison)
    if comparison["classification"] == NOT_COMPARABLE and not args.force:
        return EXIT_NOT_COMPARABLE
    return EXIT_OK


def cmd_baseline(args: argparse.Namespace) -> int:
    """Save a result as a named baseline for regression checks."""
    try:
        result = load_result(Path(args.result))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        fail(str(exc))
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
        fail(f"baseline {args.baseline!r} not found at {baseline_path}")
        return EXIT_USAGE_ERROR
    try:
        baseline = load_result(baseline_path)
        candidate = load_result(Path(args.candidate))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        fail(str(exc))
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
        echo_json(report.to_dict())
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


def cmd_analyze(args: argparse.Namespace) -> int:
    """Bottleneck analysis from a result's measured telemetry (#22)."""
    try:
        result = load_result(Path(args.result))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        fail(str(exc))
        return EXIT_VALIDATION_ERROR
    findings = analyze_bottlenecks(result.get("metrics", {}), result.get("system", {}))
    echo_json({"run_id": result.get("run_id"), "findings": findings})
    return EXIT_OK


def cmd_fit(args: argparse.Namespace) -> int:
    """Estimate whether a model fits in available memory (#20)."""
    system = detect_system()
    ram_gb = system.get("ram_gb")
    fit_report = estimate_model_fit(
        parameters_text=args.parameters,
        quantization=args.quantization,
        available_vram_mb=system.get("gpu_vram_mb"),
        available_ram_mb=ram_gb * 1000.0 if isinstance(ram_gb, (int, float)) else None,
        context_tokens=args.context_tokens,
    )
    echo_json(fit_report)
    return EXIT_OK


def cmd_recommend(args: argparse.Namespace) -> int:
    """Recommend a configuration for this hardware (#21)."""
    system = detect_system()
    measured = load_results_dir(Path(args.results_dir)) if args.results_dir else []
    echo_json(recommend_configuration(system, measured))
    return EXIT_OK


def cmd_score(args: argparse.Namespace) -> int:
    """Composite AIHWBench Score with full component breakdown."""
    try:
        result = load_result(Path(args.result))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        fail(str(exc))
        return EXIT_VALIDATION_ERROR
    echo_json(compute_score(result))
    return EXIT_OK


def register(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
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

    score_p = sub.add_parser("score", help="Composite AIHWBench Score (heuristic)")
    score_p.add_argument("result")
    score_p.set_defaults(func=cmd_score)
