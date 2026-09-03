"""ONNX Runtime backend — real benchmarking.

Detection uses a real import of the onnxruntime package and reports
available execution providers. Benchmarking runs a local .onnx model:
model load time, warm-up + N timed inference iterations, latency
percentiles, throughput, and hardware telemetry. Token-based metrics do
not apply to generic ONNX graphs and are reported as null.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from ..telemetry import TelemetrySampler
from .base import (
    BackendError,
    BackendInfo,
    BenchmarkConfig,
    RuntimeStatus,
    file_sha256,
    new_run_id,
    resolve_input_specs,
)


def detect() -> BackendInfo:
    """Detect ONNX Runtime via package import."""
    try:
        import onnxruntime  # type: ignore[import-untyped]
    except ImportError:
        return BackendInfo(
            "onnxruntime",
            RuntimeStatus.NOT_INSTALLED,
            None,
            "pip install onnxruntime (CPU/DirectML) or onnxruntime-gpu (CUDA)",
        )
    providers = list(onnxruntime.get_available_providers())
    return BackendInfo(
        "onnxruntime",
        RuntimeStatus.AVAILABLE,
        str(getattr(onnxruntime, "__version__", None)),
        f"providers: {', '.join(providers)}",
    )


def _providers_for_device(device: str) -> list[str] | None:
    """Map a device hint to an execution-provider preference order."""
    available = _available_providers()
    if device == "cuda" and "CUDAExecutionProvider" in available:
        return ["CUDAExecutionProvider", "CPUExecutionProvider"]
    if device == "dml" and "DmlExecutionProvider" in available:
        return ["DmlExecutionProvider", "CPUExecutionProvider"]
    if device == "cpu":
        return ["CPUExecutionProvider"]
    if device == "auto":
        return None  # let ORT pick its default priority order
    raise BackendError(
        f"device {device!r} requested but no matching provider is available "
        f"(installed providers: {', '.join(available)})"
    )


def _available_providers() -> list[str]:
    import onnxruntime  # type: ignore[import-untyped]

    return list(onnxruntime.get_available_providers())


def _numpy():
    """Import numpy lazily; it is only needed when actually benchmarking."""
    try:
        import numpy

        return numpy
    except ImportError as exc:
        raise BackendError("numpy is required to run ONNX benchmarks: pip install numpy") from exc


def _make_inputs(session: Any) -> dict[str, Any]:
    """Build deterministic zero inputs for ALL declared model inputs.

    Uses the shared resolver so every input is fed to the runtime —
    first-input-only feeds mis-measure multi-input models. Dynamic or
    unknown dimensions are pinned to 1 (documented in the result).
    """
    np = _numpy()
    specs = resolve_input_specs(
        (meta.name, meta.type, list(meta.shape)) for meta in session.get_inputs()
    )
    return {name: np.zeros(s["shape"], dtype=s["dtype"]) for name, s in specs.items()}


def _declared_inputs(session: Any) -> list[dict[str, Any]]:
    """Declared-input manifest for the result's reproducibility block."""
    return [
        {"name": meta.name, "type": meta.type, "shape": list(meta.shape)}
        for meta in session.get_inputs()
    ]


def run(config: BenchmarkConfig, system: dict[str, Any]) -> dict[str, Any]:
    """Execute a full ONNX Runtime benchmark and return a schema-1.0 result."""
    info = detect()
    if info.status is not RuntimeStatus.AVAILABLE:
        raise BackendError(f"onnxruntime is not available: {info.status.value} ({info.detail})")

    model_path = config.extra.get("model_path")
    if not model_path or not Path(model_path).is_file():
        raise BackendError(
            "onnxruntime backend requires --model-path pointing to a local .onnx file"
        )

    import onnxruntime  # type: ignore[import-untyped]

    providers = _providers_for_device(config.device)
    sess_options = onnxruntime.SessionOptions()

    load_start = time.perf_counter()
    try:
        if providers:
            session = onnxruntime.InferenceSession(
                str(model_path), sess_options=sess_options, providers=providers
            )
        else:
            session = onnxruntime.InferenceSession(str(model_path), sess_options=sess_options)
    except Exception as exc:  # noqa: BLE001 - surface ORT errors cleanly
        raise BackendError(f"failed to load ONNX model: {exc}") from exc
    load_time_ms = (time.perf_counter() - load_start) * 1000.0

    active_providers = session.get_providers()
    if providers and providers[0] not in active_providers:
        raise BackendError(
            f"requested execution provider {providers[0]!r} could not be loaded "
            f"(active providers: {', '.join(active_providers)}). Install the "
            "required CUDA/cuDNN or DirectML runtime dependencies."
        )
    feed = _make_inputs(session)
    output_names = [o.name for o in session.get_outputs()]

    def infer() -> None:
        # Feed ALL declared inputs — a first-input-only feed silently
        # mis-measures multi-input models.
        session.run(output_names, feed)

    sampler = TelemetrySampler(interval_seconds=0.5)
    sampler.start()
    latencies: list[float] = []
    try:
        for _ in range(config.warmup_runs):
            infer()
        for _ in range(config.iterations):
            start = time.perf_counter()
            infer()
            latencies.append((time.perf_counter() - start) * 1000.0)
    finally:
        sampler.stop()

    from ..metrics import percentile, performance_per_watt
    from ..versions import CURRENT_SCHEMA_VERSION

    telemetry = sampler.summary()
    mean_latency = sum(latencies) / len(latencies)
    throughput_ips = (1000.0 / mean_latency) if mean_latency > 0 else None

    metrics: dict[str, Any] = {
        "load_time_ms": round(load_time_ms, 2),
        "ttft_ms": None,
        "prompt_tokens_per_second": None,
        "generation_tokens_per_second": None,
        "total_latency_ms": round(mean_latency, 2),
        "p50_latency_ms": (round(v, 2) if (v := percentile(latencies, 50)) is not None else None),
        "p95_latency_ms": (round(v, 2) if (v := percentile(latencies, 95)) is not None else None),
        "peak_ram_mb": telemetry["peak_ram_mb"],
        "peak_vram_mb": telemetry["peak_vram_mb"],
        "avg_cpu_util_percent": telemetry["avg_cpu_util_percent"],
        "avg_gpu_util_percent": telemetry["avg_gpu_util_percent"],
        "max_temperature_c": telemetry["max_temperature_c"],
        "average_power_watts": telemetry["average_power_watts"],
        # Throughput for graph models is inferences/second, not tokens/second.
        "performance_per_watt": performance_per_watt(
            throughput_ips, telemetry["average_power_watts"]
        ),
        "throughput_inferences_per_second": round(throughput_ips, 2) if throughput_ips else None,
    }

    return {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "run_id": new_run_id("onnxruntime"),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "system": system,
        "runtime": {
            "name": "onnxruntime",
            "version": info.version,
            "backend": f"execution-providers:{','.join(active_providers)}",
            "device": config.device,
        },
        "model": {
            "name": Path(model_path).name,
            "format": "onnx",
            "quantization": None,
            "parameters": None,
            "checksum": file_sha256(model_path),
        },
        "metrics": metrics,
        "telemetry": sampler.provenance(),
        "reproducibility": {
            "prompt": None,
            "max_tokens": None,
            "temperature": None,
            "seed": None,
            "context_length": None,
            "warmup_runs": config.warmup_runs,
            "iterations": config.iterations,
            "command": (
                f"aihwbench benchmark --runtime onnxruntime --model-path {model_path} "
                f"--device {config.device}"
            ),
            "workload_type": "graph-inference",
            "graph_inputs": _declared_inputs(session),
        },
        "iterations": [
            {"iteration": i, "latency_ms": round(v, 2)} for i, v in enumerate(latencies)
        ],
    }
