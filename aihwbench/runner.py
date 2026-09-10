"""Benchmark runner — orchestrates a full benchmark execution."""

from __future__ import annotations

import json
import platform
import subprocess
import uuid
from pathlib import Path
from typing import Any

from . import PROTOCOL_VERSION
from .schemas import validate_or_raise


def git_commit() -> str | None:
    """Current git commit hash of this repository, if available."""
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5.0,
            encoding="utf-8",
            errors="replace",
        )
        if proc.returncode == 0:
            return proc.stdout.strip()
    except OSError:
        pass
    return None


def power_profile() -> str | None:
    """Windows power scheme name (reproducibility metadata)."""
    if platform.system() != "Windows":
        return None
    try:
        proc = subprocess.run(
            ["powercfg", "/getactivescheme"],
            capture_output=True,
            text=True,
            timeout=5.0,
            encoding="utf-8",
            errors="replace",
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip().splitlines()[-1]
    except OSError:
        pass
    return None


def run_benchmark(runtime: str, config: Any) -> dict[str, Any]:
    """Run one benchmark end-to-end and return a validated result document.

    Derived analyses (energy, thermal) are attached here rather than in each
    backend: they read the measured metrics and telemetry trace that every
    backend already produces, so computing them centrally keeps one
    implementation instead of five, and means a new backend gets them free.
    """
    from .analysis.battery import battery_profile
    from .analysis.energy import compute_energy_metrics
    from .analysis.thermal import thermal_from_trace
    from .backends import resolve
    from .fidelity import output_fidelity
    from .metrics import streaming_latency_metrics
    from .npu import npu_telemetry
    from .provenance import compute_provenance
    from .system_info import detect_system
    from .telemetry import sample_idle_power, trace_series

    backend = resolve(runtime)
    system = detect_system()

    # Measured before the benchmark's own load, so joules-per-token can be
    # reported net of the machine's idle draw. Skippable for quick runs;
    # when skipped the incremental figures are None rather than guessed.
    idle_seconds = float(getattr(config, "extra", {}).get("idle_baseline_seconds", 2.0))
    idle = (
        sample_idle_power(idle_seconds)
        if idle_seconds > 0
        else {"watts": None, "samples": 0, "source": None}
    )

    result: dict[str, Any] = backend.run(config, system)

    # Enrich with environment/reproducibility metadata.
    result.setdefault("run_id", f"{runtime}-{uuid.uuid4().hex[:8]}")
    result["git_commit"] = git_commit()
    result["protocol_version"] = PROTOCOL_VERSION
    repro = result.setdefault("reproducibility", {})
    repro.setdefault("python_version", platform.python_version())
    repro.setdefault("power_profile", power_profile())

    # Which workload produced this. `reproducibility.prompt` already carries
    # the text and is part of the comparison key, but the text alone does not
    # say what the run was *for*: a 512-token generation prompt and a
    # 29-token chat prompt measure different things, and only the workload's
    # identity says which was intended. Recorded when the caller named one --
    # never inferred, since a prompt that resembles a workload's is not that
    # workload.
    workload = (getattr(config, "extra", {}) or {}).get("workload")
    if workload is not None:
        result["workload"] = {
            "id": workload.id,
            "version": workload.version,
            "kind": workload.kind,
            "osl_tokens": workload.osl_tokens,
            "isl_tokens": workload.isl_tokens,
        }

    metrics = result.setdefault("metrics", {})
    if idle["watts"] is not None:
        metrics.setdefault("idle_power_watts", idle["watts"])

    iterations = result.get("iterations") or []

    # Inter-token latency as a distribution. A mean cannot show a stall, and a
    # stall is what makes a stream feel slow.
    metrics.update(streaming_latency_metrics(iterations))

    # A speed number from a quantized run must not travel without a quality
    # signal: lowering precision makes a model faster AND changes what it
    # says. Determinism and an output fingerprint are measurable on every run
    # without a reference dataset.
    result["quality"] = output_fidelity([it.get("text") for it in iterations])

    # The raw text and per-token timing arrays did their job above. Neither
    # belongs in a published result: unbounded size, unbounded content, and a
    # hash answers every question the dataset needs to ask of the text.
    for iteration in iterations:
        iteration.pop("text", None)
        iteration.pop("chunk_times_ms", None)

    telemetry = result.get("telemetry") or {}
    sources = telemetry.get("sources") or {}
    power_source = sources.get("power_watts") or idle.get("source")
    result["energy"] = compute_energy_metrics(
        average_power_watts=metrics.get("average_power_watts"),
        idle_power_watts=idle["watts"],
        generation_tokens_per_second=metrics.get("generation_tokens_per_second"),
        requests_per_second=None,
        telemetry_source=power_source if isinstance(power_source, str) else None,
    )
    result["energy"]["idle_baseline"] = idle

    # Whether this machine has an NPU, and whether anything measured it.
    #
    # Copilot+ and Apple Intelligence are pushing NPUs into mainstream
    # hardware, and no vendor yet exposes a portable utilization or power
    # counter. Silence about that is worse than an honest null: a reader
    # comparing a result from an NPU-equipped laptop against one without has
    # no way to know the difference exists, and a reader seeing no NPU
    # metrics cannot tell "this machine has none" from "nobody measured it".
    # The block says which, and never invents a number.
    result["npu"] = npu_telemetry(system)

    trace = trace_series(result)
    result["thermal"] = thermal_from_trace(trace)
    # Only meaningful unplugged; on mains power it says so rather than
    # reporting a drain rate of zero.
    result["battery"] = battery_profile(trace)

    # Last, because the hash covers the whole document: every enrichment
    # above has to be in place first. compute_provenance excludes the
    # provenance block itself, so the hash is not self-referential.
    #
    # This was previously computed only by `aihwbench bundle`, so every result
    # produced by a benchmark run carried no hash at all and could not be
    # checked for tampering -- the data-quality report's provenance check
    # failed on all six published results for that reason.
    result["provenance"] = compute_provenance(
        result,
        environment=result.get("system"),
        workload=result.get("reproducibility"),
        model_identity=result.get("model"),
    )

    validate_or_raise(result)
    return result


def save_result(result: dict[str, Any], directory: Path) -> Path:
    """Write a result document to a results directory."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{result['run_id']}.json"
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return path
