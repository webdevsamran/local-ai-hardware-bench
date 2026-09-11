"""Benchmark execution commands: single runs, suites, sweeps, manifests,
capacity ladders and auto-tuning."""

from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path
from typing import Any

from ..agentic import AGENTIC_SCRIPTS, run_agentic_loop
from ..analysis.cliff import find_offload_cliff
from ..analysis.context import analyze_context_scaling
from ..analysis.kvcache import analyze_kv_cache_matrix
from ..analysis.perplexity import measure_perplexity
from ..analysis.tune import (
    TUNING_AXES,
    UnsupportedAxisError,
    check_axes_supported,
    run_tuner,
)
from ..backends import (
    BACKENDS,
    BackendError,
    BenchmarkConfig,
    backend_tunable_axes,
    resolve,
)
from ..capacity import CapacityConfig, run_capacity_ladder
from ..exit_codes import EXIT_OK, EXIT_USAGE_ERROR, EXIT_VALIDATION_ERROR
from ..gguf import read_gguf_attention
from ..manifests import ExperimentError, load_experiment
from ..rag import run_rag_pipeline
from ..report import render_report
from ..runner import run_benchmark, save_result
from ..suites import list_suites, load_suite, run_suite
from ..sweep import SweepSpec, matrix_to_csv_rows, run_sweep
from ..system_info import detect_system
from ..workloads import get_workload, list_workloads
from ..workloads.builtin import synthesize_prompt
from .common import echo_json, fail

#: The `benchmark --max-tokens` default. Named so a workload's declared output
#: length can tell an explicit --max-tokens from an untouched default.
_DEFAULT_MAX_TOKENS = 128

#: The `benchmark --context-length` default, named for the same reason as
#: `_DEFAULT_MAX_TOKENS`: a workload needs to tell an explicit setting from an
#: untouched one before it may raise it.
_DEFAULT_CONTEXT_LENGTH = 2048


def _workload_prompt(workload: Any) -> str | None:
    """The request text for a workload, synthesized where it declares a length.

    A workload either carries a prompt or declares how long its input should
    be. Only the first kind used to be runnable, so eight registered profiles
    -- `long_prompt`, `long_context`, `decode_only`, `prefill_only` and the
    rest -- could not be executed at all, while `synthesize_prompt` sat in
    `workloads/builtin.py` with no callers.

    Synthesis is deterministic for a given length and seed, so two machines
    running `long_prompt` send the same bytes. That is what makes the profile
    a comparable measurement rather than two people each inventing 4096 tokens
    of their own.

    Returns None for a workload that is neither -- a multi-turn conversation,
    a traffic mix, an agentic loop -- because those need a driver rather than
    a single request, and `benchmark` is not it.
    """
    if workload.prompt:
        return str(workload.prompt)
    if workload.turns or workload.traffic_mix:
        return None
    if workload.isl_tokens:
        return synthesize_prompt(int(workload.isl_tokens))
    return None


def _runnable_workloads() -> list[Any]:
    """Registered workloads `benchmark` can actually run.

    A conversation, a traffic mix or an agentic loop needs a driver that
    issues more than one request; offering those here would let someone run
    `multi_turn_8` and measure a single turn while believing they measured
    eight. They are reached through `aihwbench run`, `agentic` and `rag`.
    """
    runnable = []
    for workload_id in list_workloads():
        try:
            workload = get_workload(workload_id)
        except KeyError:  # pragma: no cover - registry mutated mid-call
            continue
        if _workload_prompt(workload):
            runnable.append(workload)
    return runnable


def cmd_benchmark(args: argparse.Namespace) -> int:
    if args.runtime == "ollama" and not args.model:
        fail("--model is required for the ollama runtime")
        return EXIT_USAGE_ERROR
    if args.runtime in ("llama.cpp", "onnxruntime", "openvino") and not args.model_path:
        fail(f"--model-path is required for the {args.runtime} runtime")
        return EXIT_USAGE_ERROR
    # `BenchmarkConfig.prompt` has always existed and always been left at its
    # default here, so the prompt -- which is part of the comparison key --
    # was the one benchmark parameter no user could set.
    prompt = args.prompt
    workload = None
    workload_id = getattr(args, "workload", None)
    if workload_id:
        if prompt:
            fail("--prompt and --workload set the same thing; pass only one")
            return EXIT_USAGE_ERROR
        try:
            workload = get_workload(workload_id)
        except KeyError:
            fail(f"unknown workload {workload_id!r}; see `aihwbench run --help`")
            return EXIT_USAGE_ERROR
        prompt = _workload_prompt(workload)
        if not prompt:
            fail(
                f"workload {workload_id!r} needs more than one request -- a "
                "conversation, a traffic mix or an agentic loop -- so "
                "`benchmark` cannot run it. See `aihwbench run`, `agentic` "
                "or `rag`."
            )
            return EXIT_USAGE_ERROR
        # A workload's declared output length is part of what it measures, so
        # honour it unless the caller asked for something specific.
        if workload.osl_tokens and args.max_tokens == _DEFAULT_MAX_TOKENS:
            args.max_tokens = workload.osl_tokens

        # And the context has to hold what the workload sends.
        #
        # `long_prompt` declares 4096 input tokens and ran at the 2048-token
        # default, so the server truncated a 3331-token prompt to 1026 and the
        # result reported prefill throughput for a third of the intended
        # input. Nothing flagged it: `workload.isl_tokens` said 4096,
        # `metrics.prompt_tokens` said 1026, and the two never met.
        needed = (workload.isl_tokens or 0) + (workload.osl_tokens or 0)
        if needed > args.context_length == _DEFAULT_CONTEXT_LENGTH:
            args.context_length = needed

    config = BenchmarkConfig(
        model=args.model or "",
        max_tokens=args.max_tokens,
        warmup_runs=args.warmup,
        iterations=args.iterations,
        temperature=args.temperature,
        seed=args.seed,
        context_length=args.context_length,
        device=args.device,
        extra={"model_path": args.model_path, "workload": workload},
        **({"prompt": prompt} if prompt else {}),
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


def _sweep_axes(path: Path) -> dict[str, Any] | None:
    """The axes a saved sweep covers, or None if there is no readable sweep."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    axes = data.get("axes") if isinstance(data, dict) else None
    return axes if isinstance(axes, dict) else None


def cmd_sweep(args: argparse.Namespace) -> int:
    """Run a parameter sweep over one runtime/model (#5)."""
    axes: dict[str, tuple[Any, ...]] = {}
    if args.max_tokens_list:
        axes["max_tokens"] = tuple(int(v) for v in args.max_tokens_list.split(","))
    if args.iterations_list:
        axes["iterations"] = tuple(int(v) for v in args.iterations_list.split(","))
    if args.context_list:
        axes["context_length"] = tuple(int(v) for v in args.context_list.split(","))
    if args.device_list:
        axes["device"] = tuple(args.device_list.split(","))
    if args.gpu_layers_list:
        axes["gpu_layers"] = tuple(int(v) for v in args.gpu_layers_list.split(","))
    for which in ("k", "v"):
        raw = getattr(args, f"cache_type_{which}_list", None)
        if raw:
            axes[f"cache_type_{which}"] = tuple(v.strip().lower() for v in raw.split(","))
    if getattr(args, "flash_attn_list", None):
        axes["flash_attn"] = tuple(v.strip().lower() for v in args.flash_attn_list.split(","))
    if getattr(args, "threads_list", None):
        axes["threads"] = tuple(int(v) for v in args.threads_list.split(","))
    if getattr(args, "batch_list", None):
        axes["batch_size"] = tuple(int(v) for v in args.batch_list.split(","))
    if not axes:
        fail(
            "provide at least one sweep axis (--max-tokens-list/"
            "--iterations-list/--context-list/--device-list/--gpu-layers-list/"
            "--cache-type-k-list/--cache-type-v-list/--flash-attn-list/"
            "--threads-list/--batch-list)"
        )
        return EXIT_USAGE_ERROR
    # Refuse an axis the backend will not apply, for the same reason the tuner
    # does: sweeping an inert parameter measures run-to-run variance and
    # presents it as a difference between configurations.
    try:
        check_axes_supported(
            {k: v for k, v in axes.items() if k in TUNING_AXES},
            backend_tunable_axes(args.runtime),
            args.runtime,
        )
    except UnsupportedAxisError as exc:
        fail(str(exc))
        return EXIT_USAGE_ERROR
    # What was swept, recorded whichever flag named it. Runtimes taking a
    # `--model-path` left `model` empty, so a published cliff curve arrived
    # with no model attached -- and a cliff curve without one is
    # uninterpretable, since where throughput collapses depends entirely on
    # how big the model is.
    model_identity = args.model or (Path(args.model_path).name if args.model_path else "")
    out_dir = Path(args.output)
    stem = getattr(args, "output_name", None) or f"sweep-{args.runtime}"
    out_path = out_dir / f"{stem}.json"

    # Refuse before measuring, not after. The output name is derived from the
    # runtime alone, so a second sweep of the same runtime lands on the first
    # one's file -- and the first may be published data somebody has cited. A
    # re-run of the *same* axes is a re-measurement and overwrites happily;
    # different axes are a different experiment and need their own name.
    existing_axes = _sweep_axes(out_path)
    if existing_axes is not None and set(existing_axes) != set(axes):
        fail(
            f"{out_path} already holds a sweep over {sorted(existing_axes)}, and "
            f"this one sweeps {sorted(axes)}. Writing would destroy it. Pass "
            f"--output-name to give this sweep its own file."
        )
        return EXIT_USAGE_ERROR

    spec = SweepSpec(axes=axes, base={"runtime": args.runtime, "model": model_identity})

    def run_fn(point: dict[str, Any]) -> dict[str, Any]:
        config = BenchmarkConfig(
            model=point.get("model", ""),
            max_tokens=point.get("max_tokens", 128),
            iterations=point.get("iterations", 5),
            context_length=point.get("context_length", 2048),
            device=point.get("device", "auto"),
            # Forward the swept point so backend-applied axes (gpu_layers)
            # actually reach the backend.
            extra={"model_path": args.model_path, **point},
        )
        return run_benchmark(point["runtime"], config)

    matrix = run_sweep(spec, run_fn)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {
                "axes": {k: list(v) for k, v in axes.items()},
                # The environment the whole sweep ran in. Every row shares it,
                # and a sweep read on another machine is not interpretable
                # without it: the offload cliff is a property of this GPU's
                # memory and PCIe link as much as of the model.
                "environment": {
                    "runtime": args.runtime,
                    "model": model_identity,
                    "system": detect_system(),
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                },
                "matrix": matrix,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    csv_rows = matrix_to_csv_rows(matrix)
    csv_path = out_dir / f"{stem}.csv"
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


def cmd_agentic(args: argparse.Namespace) -> int:
    """Run a scripted agentic workload, timing model and tools separately."""
    script = AGENTIC_SCRIPTS.get(args.workload)
    if script is None:
        fail(
            f"unknown agentic workload {args.workload!r}; "
            f"available: {', '.join(sorted(AGENTIC_SCRIPTS))}"
        )
        return EXIT_USAGE_ERROR
    try:
        backend = resolve(args.runtime)
    except BackendError as exc:
        fail(str(exc))
        return EXIT_USAGE_ERROR

    generate = getattr(backend, "generate_text", None)
    if generate is None:
        fail(
            f"runtime {args.runtime!r} does not implement generate_text, which "
            "an agentic workload needs to drive its own multi-turn loop. "
            "Backends that stream a single completion per call can add it; "
            "graph runtimes emit no tokens and cannot run this workload."
        )
        return EXIT_USAGE_ERROR

    config = BenchmarkConfig(
        model=args.model or "",
        max_tokens=args.max_tokens,
        iterations=1,
        warmup_runs=0,
        device=args.device,
        extra={"model_path": args.model_path},
    )
    try:
        report = run_agentic_loop(lambda prompt: generate(prompt, config), script)
    except BackendError as exc:
        fail(str(exc))
        return EXIT_USAGE_ERROR

    report["workload"] = args.workload
    report["runtime"] = args.runtime
    report["model"] = args.model
    echo_json(report)
    return EXIT_OK


def cmd_rag(args: argparse.Namespace) -> int:
    """Run the RAG pipeline, timing retrieval, reranking and generation apart."""
    try:
        backend = resolve(args.runtime)
    except BackendError as exc:
        fail(str(exc))
        return EXIT_USAGE_ERROR

    generate = getattr(backend, "generate_text", None)
    if generate is None:
        fail(
            f"runtime {args.runtime!r} does not implement generate_text, which "
            "the RAG workload needs to issue its own assembled prompts. Graph "
            "runtimes emit no tokens and cannot run this workload."
        )
        return EXIT_USAGE_ERROR

    config = BenchmarkConfig(
        model=args.model or "",
        max_tokens=args.max_tokens,
        iterations=1,
        warmup_runs=0,
        device=args.device,
        extra={"model_path": args.model_path},
    )
    try:
        report = run_rag_pipeline(lambda prompt: generate(prompt, config), top_k=args.top_k)
    except BackendError as exc:
        fail(str(exc))
        return EXIT_USAGE_ERROR

    report["runtime"] = args.runtime
    report["model"] = args.model
    report["top_k"] = args.top_k
    echo_json(report)
    return EXIT_OK


def cmd_cliff(args: argparse.Namespace) -> int:
    """Locate the offload cliff in a saved sweep matrix."""
    matrix = _load_matrix(Path(args.sweep))
    if matrix is None:
        return EXIT_USAGE_ERROR
    echo_json(find_offload_cliff(matrix, axis=args.axis))
    return EXIT_OK


def cmd_kv_cache(args: argparse.Namespace) -> int:
    """Report what KV-cache quantization costs in memory, and what it buys.

    Leads with bytes, because that is what the setting actually changes. A
    throughput column appears with its noise floor attached; a difference
    inside that floor is not a difference.
    """
    try:
        data = json.loads(Path(args.sweep).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(str(exc))
        return EXIT_USAGE_ERROR
    if not isinstance(data, dict) or not isinstance(data.get("matrix"), list):
        fail(f"{args.sweep}: expected a sweep file with a 'matrix' array")
        return EXIT_USAGE_ERROR

    geometry = read_gguf_attention(args.model_path) if args.model_path else None
    if args.model_path and not (geometry or {}).get("block_count"):
        # Without geometry the analytic column is absent, and the analytic
        # column is the point. Say so rather than printing a table that
        # quietly answers a smaller question.
        fail(
            f"{args.model_path}: no attention geometry in this GGUF header, so "
            "the cache size cannot be computed. The measured VRAM column alone "
            "cannot separate the cache from everything else on the device."
        )
        return EXIT_VALIDATION_ERROR

    report = analyze_kv_cache_matrix(data, geometry, args.context)
    if getattr(args, "json", False):
        echo_json(report)
        return EXIT_OK

    if report.get("unresolved"):
        print(report["unresolved"])
        return EXIT_VALIDATION_ERROR

    context = report.get("context_length")
    print(f"KV-cache quantization at {context or '?'} tokens of context")
    print()
    print(
        f"{'K':<6} {'V':<6} {'cache MiB':>10} {'saved':>8} {'VRAM MiB':>9} {'tok/s':>9} {'vs f16':>8}"
    )
    for entry in report["configurations"]:
        cache = entry.get("kv_cache_mb")
        saved = entry.get("kv_cache_saved_percent")
        vram = entry.get("peak_vram_mb")
        tps = entry.get("generation_tokens_per_second")
        change = entry.get("throughput_change_percent")
        marker = "" if entry.get("throughput_distinguishable") else " ~"
        # A setting reached for to save memory that spends it instead is the
        # one row a reader must not skim past.
        warn = " !" if entry.get("costs_more_than_baseline") else "  "
        print(
            f"{entry['cache_type_k']:<6} {entry['cache_type_v']:<6} "
            f"{cache if cache is not None else '-':>10} "
            f"{(f'{saved:.0f}%' if saved is not None else '-'):>8} "
            f"{vram if vram is not None else '-':>9}{warn}"
            f"{(f'{tps:.1f}' if tps is not None else '-'):>9} "
            f"{(f'{change:+.1f}%{marker}' if change is not None else '-'):>8}"
        )
    print()
    print("~ inside the run-to-run noise floor: indistinguishable, not equal")
    inverted = [c for c in report["configurations"] if c.get("costs_more_than_baseline")]
    if inverted:
        print("! uses MORE memory than the baseline despite a smaller cache:")
        for entry in inverted:
            print(
                f"    {entry['cache_type_k']}/{entry['cache_type_v']}: {entry['measurement_note']}"
            )
    print()
    print(report["framing"])
    return EXIT_OK


def cmd_perplexity(args: argparse.Namespace) -> int:
    """Measure perplexity over a corpus, recording what makes it comparable.

    Perplexity is per token, so two models with different tokenizers produce
    numbers on different scales. The report carries the tokenizer identity and
    the corpus hash so a later comparison can be checked rather than assumed.
    """
    report = measure_perplexity(
        args.model_path,
        args.corpus,
        context_length=args.context,
        chunks=args.chunks,
        gpu_layers=args.gpu_layers,
    )
    echo_json(report)
    return EXIT_OK if report.get("perplexity") is not None else EXIT_VALIDATION_ERROR


def _load_matrix(path: Path) -> list[dict[str, Any]] | None:
    """Read a sweep matrix, tolerating either the file or a bare array."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(str(exc))
        return None
    matrix = data.get("matrix") if isinstance(data, dict) else data
    if not isinstance(matrix, list):
        fail(f"{path}: expected a sweep file with a 'matrix' array")
        return None
    return matrix


def cmd_context_scaling(args: argparse.Namespace) -> int:
    """Analyse how performance degrades as context depth grows."""
    matrix = _load_matrix(Path(args.sweep))
    if matrix is None:
        return EXIT_USAGE_ERROR
    echo_json(analyze_context_scaling(matrix, axis=args.axis, min_acceptable_tps=args.min_tps))
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

    def execute(_request_id: int) -> dict[str, Any]:
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
    axes: dict[str, tuple[Any, ...]] = {}
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

    def run_fn(point: dict[str, Any]) -> dict[str, Any]:
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
        report = run_tuner(
            axes,
            run_fn,
            supported_axes=backend_tunable_axes(args.runtime),
            runtime=args.runtime,
        )
    except UnsupportedAxisError as exc:
        fail(str(exc))
        return EXIT_USAGE_ERROR
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


def register(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    bench = sub.add_parser("benchmark", help="Run a real benchmark")
    bench.add_argument("--runtime", required=True, choices=sorted(BACKENDS))
    bench.add_argument("--model", default=None, help="Model identifier (e.g. ollama tag)")
    bench.add_argument("--model-path", default=None, help="Local model file path (llama.cpp)")
    bench.add_argument("--max-tokens", type=int, default=_DEFAULT_MAX_TOKENS)
    bench.add_argument(
        "--prompt",
        default=None,
        help=(
            "Prompt to benchmark. Recorded in the result and part of the "
            "comparison key, so two runs with different prompts are never "
            "ranked against each other."
        ),
    )
    bench.add_argument(
        "--workload",
        default=None,
        choices=sorted(w.id for w in _runnable_workloads()),
        help=(
            "A registered workload to run instead of the default prompt. "
            "Sets the prompt and, unless --max-tokens says otherwise, the "
            "target output length."
        ),
    )
    bench.add_argument("--warmup", type=int, default=2)
    bench.add_argument("--iterations", type=int, default=5)
    bench.add_argument("--temperature", type=float, default=0.0)
    bench.add_argument("--seed", type=int, default=42)
    bench.add_argument("--context-length", type=int, default=_DEFAULT_CONTEXT_LENGTH)
    bench.add_argument("--device", default="auto", help="auto | cpu | cuda | gpu | npu")
    bench.add_argument(
        "--output",
        default="results",
        help=(
            "Directory. The result is written to <output>/raw/ and its report "
            "to <output>/. Passing a file path here silently creates a "
            "directory with that name."
        ),
    )
    bench.set_defaults(func=cmd_benchmark)

    suite_p = sub.add_parser("suite", help="Run a versioned benchmark suite profile")
    suite_p.add_argument("name", nargs="?", default=None, help="Suite name (e.g. smoke)")
    suite_p.add_argument("--list", action="store_true", help="List available suites")
    suite_p.add_argument("--runtime", default="ollama")
    suite_p.add_argument("--model", default=None, help="Model identifier (ollama tag)")
    suite_p.add_argument(
        "--model-path", default=None, help="Local model file path (llama.cpp/ONNX/OpenVINO)"
    )
    suite_p.add_argument(
        "--output", default="results", help="Directory for the suite's result files"
    )
    suite_p.set_defaults(func=cmd_suite)

    sweep_p = sub.add_parser("sweep", help="Parameter sweep producing a structured matrix")
    sweep_p.add_argument("--runtime", required=True, choices=sorted(BACKENDS))
    sweep_p.add_argument("--model", default=None)
    sweep_p.add_argument("--model-path", default=None)
    sweep_p.add_argument("--max-tokens-list", default=None, help="Comma-separated values")
    sweep_p.add_argument("--iterations-list", default=None, help="Comma-separated values")
    sweep_p.add_argument("--context-list", default=None, help="Comma-separated values")
    sweep_p.add_argument("--device-list", default=None, help="Comma-separated values")
    sweep_p.add_argument(
        "--gpu-layers-list",
        default=None,
        help=(
            "Comma-separated GPU layer counts, e.g. 0,8,16,24,99. Maps the "
            "offload cliff: where throughput collapses as the model stops "
            "fitting in VRAM. Analyse with `aihwbench cliff`."
        ),
    )
    sweep_p.add_argument(
        "--flash-attn-list",
        default=None,
        help=(
            "Comma-separated flash-attention modes: on,off,auto. The llama.cpp "
            "default is auto, and auto is not on: it declines flash attention "
            "for kernel combinations it does not cover, and the fallback can "
            "cost far more memory than the setting you were tuning saves."
        ),
    )
    sweep_p.add_argument(
        "--threads-list",
        default=None,
        help="Comma-separated CPU thread counts, e.g. 4,8,14.",
    )
    sweep_p.add_argument(
        "--batch-list",
        default=None,
        help="Comma-separated logical batch sizes, e.g. 128,512,2048.",
    )
    for which in ("k", "v"):
        sweep_p.add_argument(
            f"--cache-type-{which}-list",
            default=None,
            help=(
                f"Comma-separated KV-cache dtypes for {which.upper()}, e.g. "
                "f16,q8_0,q4_0. Quantizing the cache is a memory setting, not "
                "a speed one: it decides how much context fits. Analyse with "
                "`aihwbench kv-cache`."
            ),
        )
    sweep_p.add_argument(
        "--output-name",
        default=None,
        help=(
            "Filename stem for this sweep, without extension. Defaults to "
            "sweep-<runtime>, which collides when one runtime is swept over "
            "more than one set of axes."
        ),
    )
    sweep_p.add_argument(
        "--output",
        default="results/sweeps",
        help="Directory; the matrix and its CSV are written as sweep-<runtime>.*",
    )
    sweep_p.set_defaults(func=cmd_sweep)

    agentic_p = sub.add_parser(
        "agentic",
        help="Run a scripted agentic workload (LLM time vs tool time)",
    )
    agentic_p.add_argument("--runtime", required=True, choices=sorted(BACKENDS))
    agentic_p.add_argument("--model", default=None)
    agentic_p.add_argument("--model-path", default=None)
    agentic_p.add_argument("--device", default="auto")
    agentic_p.add_argument("--max-tokens", type=int, default=64)
    agentic_p.add_argument(
        "--workload",
        default="agentic_swe",
        choices=sorted(AGENTIC_SCRIPTS),
    )
    agentic_p.set_defaults(func=cmd_agentic)

    rag_p = sub.add_parser(
        "rag",
        help="Run a RAG pipeline (retrieval vs rerank vs generation time)",
    )
    rag_p.add_argument("--runtime", required=True, choices=sorted(BACKENDS))
    rag_p.add_argument("--model", default=None)
    rag_p.add_argument("--model-path", default=None)
    rag_p.add_argument("--device", default="auto")
    rag_p.add_argument("--max-tokens", type=int, default=192)
    rag_p.add_argument("--top-k", type=int, default=4, help="Passages retrieved per question")
    rag_p.set_defaults(func=cmd_rag)

    cliff_p = sub.add_parser("cliff", help="Find the offload cliff in a sweep matrix")
    cliff_p.add_argument("sweep", help="Path to a sweep-*.json produced by `aihwbench sweep`")
    cliff_p.add_argument("--axis", default="gpu_layers")
    cliff_p.set_defaults(func=cmd_cliff)

    kv_p = sub.add_parser(
        "kv-cache",
        help="What KV-cache quantization costs in memory, and what context it buys",
    )
    kv_p.add_argument("sweep", help="Sweep file produced by `aihwbench sweep`")
    kv_p.add_argument(
        "--model-path",
        default=None,
        help=(
            "GGUF file whose attention geometry sizes the cache. Without it "
            "only the measured device VRAM is reported, which cannot separate "
            "the cache from anything else resident."
        ),
    )
    kv_p.add_argument(
        "--context",
        type=int,
        default=None,
        help="Context length to size the cache for (default: the sweep's own)",
    )
    kv_p.add_argument("--json", action="store_true", help="Emit the report as JSON")
    kv_p.set_defaults(func=cmd_kv_cache)

    ppl_p = sub.add_parser(
        "perplexity",
        help="Perplexity over a corpus, with what makes it comparable recorded",
    )
    ppl_p.add_argument("--model-path", required=True, help="GGUF model file")
    ppl_p.add_argument(
        "--corpus",
        required=True,
        help=(
            "Text file to measure over. Supplied by you: this project bundles "
            "no datasets, and a perplexity figure over a corpus nobody names "
            "is not a result."
        ),
    )
    ppl_p.add_argument("--context", type=int, default=512)
    ppl_p.add_argument("--chunks", type=int, default=None, help="Default: the whole corpus")
    ppl_p.add_argument("--gpu-layers", type=int, default=99)
    ppl_p.set_defaults(func=cmd_perplexity)

    ctx_p = sub.add_parser(
        "context-scaling",
        help="Analyse a context-length sweep: prefill degradation and memory saturation",
    )
    ctx_p.add_argument("sweep", help="Path to a sweep-*.json produced by `aihwbench sweep`")
    ctx_p.add_argument("--axis", default="context_length")
    ctx_p.add_argument(
        "--min-tps",
        type=float,
        default=None,
        help="Throughput floor, to report the deepest context still above it",
    )
    ctx_p.set_defaults(func=cmd_context_scaling)

    run_p = sub.add_parser("run", help="Run a declarative experiment manifest (JSON/TOML/YAML)")
    run_p.add_argument("manifest")
    run_p.add_argument("--iterations", type=int, default=5)
    run_p.add_argument("--model-path", default=None)
    run_p.add_argument(
        "--output", default="results/experiments", help="Directory for experiment output"
    )
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
    tune_p.add_argument(
        "--output",
        default="results/tuning",
        help="Directory; the report is written as tune-<runtime>.json",
    )
    tune_p.set_defaults(func=cmd_tune)
