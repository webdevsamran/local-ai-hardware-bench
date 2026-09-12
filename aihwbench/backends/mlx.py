"""Apple MLX — unified memory, which changes what a memory number means.

MLX is Apple's array framework for M-series silicon, and the reason it matters
to this project is not only speed. On a discrete GPU, "will this model fit" has
a hard answer: VRAM is a fixed number and exceeding it means offload or
failure. On Apple Silicon the GPU and CPU share one pool, so a 36 GB machine
can hold a model no 16 GB card can, and the offload cliff this project maps
elsewhere simply does not exist in the same shape.

So a result here records peak memory from MLX itself rather than leaving
`peak_vram_mb` to a GPU tool that has nothing to look at. Reporting an Apple
machine's graphics memory as absent would be true of the field and wrong about
the machine.

Detection separates the two failures that get conflated — not Apple Silicon at
all, and Apple Silicon without the Python stack — because only the second is
something a user can fix in a minute.

**Written, not observed.** No Apple machine has been available to this
project; the generation path targets `mlx_lm`'s streaming API and has never
run. `docs/hardware-needed.md` lists it.
"""

from __future__ import annotations

import platform
import sys
import time
from typing import Any

from .base import (
    BackendError,
    BackendInfo,
    BenchmarkConfig,
    RuntimeStatus,
    new_run_id,
    run_command,
)


def detect() -> BackendInfo:
    """Detect MLX availability (Apple Silicon + mlx-lm package)."""
    if platform.system() != "Darwin":
        return BackendInfo(
            "mlx",
            RuntimeStatus.HARDWARE_REQUIRED,
            None,
            "Requires a Mac with Apple Silicon (M1/M2/M3/M4); see https://github.com/ml-explore/mlx",
        )
    if platform.machine() != "arm64":
        return BackendInfo(
            "mlx",
            RuntimeStatus.HARDWARE_REQUIRED,
            None,
            "MLX requires Apple Silicon (arm64); Intel Macs are not supported",
        )
    code, _out = run_command([sys.executable, "-c", "import mlx_lm"], timeout=30.0)
    if code == 0:
        return BackendInfo("mlx", RuntimeStatus.AVAILABLE, None, "mlx_lm importable")
    # `mlx.core` without `mlx_lm` is a real state and a different fix: the
    # array framework is there, the language-model layer is not.
    code, _out = run_command([sys.executable, "-c", "import mlx.core"], timeout=30.0)
    if code == 0:
        return BackendInfo(
            "mlx",
            RuntimeStatus.CONFIGURATION_REQUIRED,
            None,
            "mlx core is importable but mlx_lm is not: pip install mlx-lm",
        )
    return BackendInfo(
        "mlx",
        RuntimeStatus.CONFIGURATION_REQUIRED,
        None,
        "Install the MLX Python stack: pip install mlx-lm",
    )


def _one_iteration(
    model: Any, tokenizer: Any, stream_generate: Any, config: BenchmarkConfig
) -> dict[str, Any]:
    """One measured generation, shaped like every other LLM backend's.

    The keys are the ones `metrics.aggregate_iteration_metrics` reads, so MLX
    inherits the same interval, percentile and fidelity treatment as Ollama
    rather than a second interpretation of what TTFT means.

    MLX reports its own prompt and generation token counts and rates on every
    streamed response, and the *last* response carries the totals — so the
    counts come from the runtime rather than from counting chunks, which is a
    thing this project refuses to do everywhere else.
    """
    chunk_times_ms: list[float] = []
    parts: list[str] = []
    final: Any = None
    peak_memory_gb: float | None = None

    start = time.perf_counter()
    for response in stream_generate(
        model, tokenizer, prompt=config.prompt, max_tokens=config.max_tokens
    ):
        text = getattr(response, "text", None)
        if text:
            chunk_times_ms.append((time.perf_counter() - start) * 1000.0)
            parts.append(text)
        final = response
    total_ms = (time.perf_counter() - start) * 1000.0

    prompt_tokens = getattr(final, "prompt_tokens", None)
    generation_tokens = getattr(final, "generation_tokens", None)
    prompt_tps = getattr(final, "prompt_tps", None)
    generation_tps = getattr(final, "generation_tps", None)
    peak_memory_gb = getattr(final, "peak_memory", None)

    return {
        "ttft_ms": round(chunk_times_ms[0], 2) if chunk_times_ms else None,
        "total_latency_ms": round(total_ms, 2),
        "completion_tokens": generation_tokens,
        # Derived from the runtime's own rate rather than from wall clock, so
        # generation throughput is not diluted by prefill.
        "eval_seconds": (
            (generation_tokens / generation_tps) if generation_tokens and generation_tps else None
        ),
        "prompt_tokens": prompt_tokens,
        "prompt_eval_seconds": (
            (prompt_tokens / prompt_tps) if prompt_tokens and prompt_tps else None
        ),
        "load_time_ms": None,
        # Unified memory: this is the whole machine's peak for the process, not
        # a separate graphics pool, and that is the point.
        "peak_memory_gb": peak_memory_gb,
        "chunk_times_ms": [round(t, 3) for t in chunk_times_ms],
        "text": "".join(parts),
    }


def run(config: BenchmarkConfig, system: dict[str, Any]) -> dict[str, Any]:
    """Benchmark an MLX model on Apple Silicon."""
    info = detect()
    if info.status is not RuntimeStatus.AVAILABLE:
        raise BackendError(f"mlx is not available: {info.status.value} ({info.detail})")

    model_ref = (config.extra or {}).get("model_path") or config.model
    if not model_ref:
        raise BackendError(
            "mlx needs a model: pass --model with an mlx-community HuggingFace id "
            "(for example mlx-community/Qwen2.5-0.5B-Instruct-4bit) or --model-path "
            "with a local MLX model directory."
        )

    try:
        from mlx_lm import load, stream_generate
    except ImportError as exc:
        raise BackendError(
            f"mlx_lm is not importable ({exc}). Install it with: pip install mlx-lm"
        ) from exc

    from ..metrics import aggregate_iteration_metrics, performance_per_watt
    from ..telemetry import TelemetrySampler
    from ..versions import CURRENT_SCHEMA_VERSION

    load_start = time.perf_counter()
    try:
        model, tokenizer = load(str(model_ref))
    except Exception as exc:  # noqa: BLE001 - surface loader errors cleanly
        raise BackendError(f"failed to load the MLX model {model_ref!r}: {exc}") from exc
    load_time_ms = (time.perf_counter() - load_start) * 1000.0

    sampler = TelemetrySampler(interval_seconds=0.5)
    sampler.start()
    iterations: list[dict[str, Any]] = []
    try:
        for _ in range(config.warmup_runs):
            _one_iteration(model, tokenizer, stream_generate, config)
        for _ in range(config.iterations):
            iterations.append(_one_iteration(model, tokenizer, stream_generate, config))
    finally:
        sampler.stop()

    metrics = aggregate_iteration_metrics(iterations)
    telemetry = sampler.summary()
    metrics.update(telemetry)
    metrics["load_time_ms"] = round(load_time_ms, 2)
    metrics["performance_per_watt"] = performance_per_watt(
        metrics.get("generation_tokens_per_second"), telemetry.get("average_power_watts")
    )

    # Peak memory from MLX itself. On unified memory there is no separate
    # graphics pool for a GPU tool to read, so leaving this to `peak_vram_mb`
    # would report the field as absent and imply the model used no device
    # memory at all.
    peaks = [it["peak_memory_gb"] for it in iterations if it.get("peak_memory_gb") is not None]
    if peaks:
        metrics["peak_unified_memory_mb"] = round(max(peaks) * 1024.0, 2)

    return {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "run_id": new_run_id("mlx"),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "system": system,
        "runtime": {
            "name": "mlx",
            "version": info.version,
            "backend": "mlx-lm",
            # Apple Silicon has one pool and one compute complex from this
            # backend's point of view; "gpu" would imply a separate device with
            # its own memory, which is the distinction that does not exist here.
            "device": "apple-silicon",
            "device_requested": config.device,
        },
        "model": {
            "name": str(model_ref),
            "format": "mlx",
            "quantization": None,
            "parameters": None,
            "checksum": None,
        },
        "metrics": metrics,
        "telemetry": sampler.provenance(),
        "reproducibility": {
            "prompt": config.prompt,
            "max_tokens": config.max_tokens,
            "temperature": config.temperature,
            "seed": config.seed,
            "context_length": config.context_length,
            "warmup_runs": config.warmup_runs,
            "iterations": config.iterations,
            "command": f"aihwbench benchmark --runtime mlx --model {model_ref}",
        },
        "iterations": iterations,
    }


#: Declared capability contract: truthful prerequisites.
CAPABILITIES: tuple[str, ...] = (
    "apple-silicon-required",
    "macos-required",
    "mlx-lm-required",
    "unified-memory",
)
