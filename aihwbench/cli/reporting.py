"""Result inspection commands: validate, report, compare, baselines,
regression gates and hardware-fit analysis."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from ..analysis import analyze_bottlenecks, estimate_model_fit, recommend_configuration
from ..analysis.cost import compare_local_vs_cloud, compute_cost_metrics
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
    valid, errors = validate_file(Path(args.result), formal=args.formal)
    if valid:
        scope = "VALID (semantic + formal schema)" if args.formal else "VALID"
        print(f"{scope}: {args.result}")
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
    report = evaluate_regression(baseline, candidate, thresholds, force=args.force)
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
    if report.status == "INCOMPARABLE":
        # Zero checks ran. Reporting success here would make the gate fail open
        # exactly when the environment drifted -- when it is needed most.
        fail(
            "baseline and candidate are NOT_COMPARABLE, so no regression checks "
            "ran. Re-baseline against a matching environment, or pass --force to "
            "gate on the metrics regardless."
        )
        return EXIT_NOT_COMPARABLE
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
    """Recommend a configuration for a machine (#21).

    Defaults to the machine this is running on, but accepts an explicit
    hardware description. "What should I run on the card I am about to buy" is
    a question people ask far more often than "what should I run on this", and
    it was unanswerable while the system was always detected.
    """
    system = detect_system()
    if args.vram_mb is not None:
        system = {**system, "gpu_vram_mb": args.vram_mb, "gpu": args.gpu or system.get("gpu")}
    if args.ram_gb is not None:
        system = {**system, "ram_gb": args.ram_gb}

    measured = load_results_dir(Path(args.results_dir)) if args.results_dir else []
    report = recommend_configuration(system, measured)
    report["for_hardware"] = {
        "gpu": system.get("gpu"),
        "gpu_vram_mb": system.get("gpu_vram_mb"),
        "ram_gb": system.get("ram_gb"),
        "described": args.vram_mb is not None or args.ram_gb is not None,
    }
    echo_json(report)
    return EXIT_OK


def cmd_cost(args: argparse.Namespace) -> int:
    """Cost per token, and local ownership against a cloud API.

    Cloud pricing is supplied by the caller rather than bundled: provider
    prices change frequently, and a stale table inside a benchmark would keep
    producing confident wrong answers.
    """
    metrics: dict[str, Any] = {}
    if args.result:
        try:
            result = load_result(Path(args.result))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            fail(str(exc))
            return EXIT_VALIDATION_ERROR
        metrics = result.get("metrics") or {}

    power = args.power_watts
    if power is None:
        power = metrics.get("average_power_watts")
    throughput = args.tokens_per_second
    if throughput is None:
        throughput = metrics.get("generation_tokens_per_second")

    report: dict[str, Any] = {
        "measured_from": args.result,
        "cost": compute_cost_metrics(
            hardware_cost_usd=args.hardware_cost,
            electricity_usd_per_kwh=args.electricity_price,
            average_power_watts=power,
            generation_tokens_per_second=throughput,
            utilization_hours_per_day=args.hours_per_day,
            years=args.years,
        ),
    }
    if args.tokens_per_month is not None and args.cloud_price is not None:
        report["local_vs_cloud"] = compare_local_vs_cloud(
            tokens_per_month=args.tokens_per_month,
            cloud_usd_per_million_tokens=args.cloud_price,
            hardware_cost_usd=args.hardware_cost,
            electricity_usd_per_kwh=args.electricity_price,
            average_power_watts=power,
            generation_tokens_per_second=throughput,
            years=args.years or 3,
        )
    echo_json(report)
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
    val.add_argument(
        "--formal",
        action="store_true",
        help=(
            "also validate against the published JSON Schema for the "
            "document's schema_version (requires the 'schema' extra)"
        ),
    )
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
    reg.add_argument(
        "--force",
        action="store_true",
        help=(
            "run threshold checks even when baseline and candidate are "
            "NOT_COMPARABLE (the classification is still reported)"
        ),
    )
    reg.set_defaults(func=cmd_regression)

    ana = sub.add_parser("analyze", help="Bottleneck analysis from measured telemetry")
    ana.add_argument("result")
    ana.set_defaults(func=cmd_analyze)

    fit_p = sub.add_parser("fit", help="Estimate model memory fit (labeled estimate)")
    fit_p.add_argument("--parameters", required=True, help="e.g. 7B, 1.5b, 350M")
    fit_p.add_argument("--quantization", required=True, help="e.g. q4_k_m, fp16")
    fit_p.add_argument("--context-tokens", type=int, default=4096)
    fit_p.set_defaults(func=cmd_fit)

    rec = sub.add_parser("recommend", help="Recommend a configuration for a machine")
    rec.add_argument("--results-dir", default=None, help="Prior results to anchor on")
    rec.add_argument(
        "--vram-mb",
        type=float,
        default=None,
        help="Describe a machine other than this one (e.g. hardware you are considering)",
    )
    rec.add_argument("--ram-gb", type=float, default=None)
    rec.add_argument("--gpu", default=None, help="Label for the described GPU")
    rec.set_defaults(func=cmd_recommend)

    cost_p = sub.add_parser("cost", help="Cost per token, and local ownership vs a cloud API")
    cost_p.add_argument(
        "--result", default=None, help="Take measured power and throughput from this result"
    )
    cost_p.add_argument("--hardware-cost", type=float, default=None, help="USD")
    cost_p.add_argument("--electricity-price", type=float, default=None, help="USD per kWh")
    cost_p.add_argument("--power-watts", type=float, default=None, help="Overrides the result")
    cost_p.add_argument(
        "--tokens-per-second", type=float, default=None, help="Overrides the result"
    )
    cost_p.add_argument("--hours-per-day", type=float, default=None)
    cost_p.add_argument("--years", type=int, default=None)
    cost_p.add_argument("--tokens-per-month", type=float, default=None)
    cost_p.add_argument(
        "--cloud-price",
        type=float,
        default=None,
        help="USD per million tokens, read from your provider today",
    )
    cost_p.set_defaults(func=cmd_cost)

    score_p = sub.add_parser("score", help="Composite AIHWBench Score (heuristic)")
    score_p.add_argument("result")
    score_p.set_defaults(func=cmd_score)
