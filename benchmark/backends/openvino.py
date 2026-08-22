"""Intel OpenVINO backend — real benchmarking.

Detection imports the openvino package and reports available devices
(CPU, GPU, NPU). Benchmarking loads a local .onnx model via OpenVINO,
compiles it for the requested device, and measures load time, warm-up +
N timed inference iterations, latency percentiles, throughput, and
hardware telemetry. Token-based metrics do not apply to generic graphs
and are reported as null.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from ..telemetry import TelemetrySampler
from .base import BackendError, BackendInfo, BenchmarkConfig, RuntimeStatus, new_run_id


def _numpy():
    """Import numpy lazily; it is only needed when actually benchmarking."""
    try:
        import numpy

        return numpy
    except ImportError as exc:
        raise BackendError(
            "numpy is required to run OpenVINO benchmarks: pip install numpy"
        ) from exc


def detect() -> BackendInfo:
    """Detect OpenVINO via package import."""
    try:
        import openvino  # type: ignore[import-untyped]
    except ImportError:
        return BackendInfo(
            "openvino",
            RuntimeStatus.NOT_INSTALLED,
            None,
            "pip install openvino; Intel NPU benchmarking additionally needs "
            "an Intel Core Ultra class CPU with the NPU driver installed",
        )
    try:
        core = openvino.Core()
        devices = list(core.get_available_devices())
    except Exception:  # noqa: BLE001 - any runtime failure means unusable
        devices = []
    detail = f"devices: {', '.join(devices)}" if devices else "no devices enumerated"
    return BackendInfo(
        "openvino",
        RuntimeStatus.AVAILABLE,
        str(getattr(openvino, "__version__", None)),
        detail,
    )


def _resolve_device(device: str, available: list[str]) -> str:
    """Map a device hint to an OpenVINO device name."""
    if device in ("auto", "cpu") or device.upper() in available:
        return "AUTO" if device == "auto" else ("CPU" if device == "cpu" else device.upper())
    if device in ("gpu", "npu"):
        # OpenVINO enumerates indexed devices such as GPU.0 / GPU.1.
        matches = [d for d in available if d.upper().startswith(device.upper())]
        if matches:
            return matches[0]
    raise BackendError(
        f"device {device!r} requested but not available (OpenVINO devices: {', '.join(available)})"
    )


def run(config: BenchmarkConfig, system: dict[str, Any]) -> dict[str, Any]:
    """Execute a full OpenVINO benchmark and return a schema-1.0 result."""
    info = detect()
    if info.status is not RuntimeStatus.AVAILABLE:
        raise BackendError(f"openvino is not available: {info.status.value} ({info.detail})")

    model_path = config.extra.get("model_path")
    if not model_path or not Path(model_path).is_file():
        raise BackendError("openvino backend requires --model-path pointing to a local .onnx file")

    import openvino as ov

    core = ov.Core()
    available = list(core.get_available_devices())
    target_device = _resolve_device(config.device, available)

    load_start = time.perf_counter()
    try:
        model = core.read_model(str(model_path))
        compiled = core.compile_model(model, target_device)
    except Exception as exc:  # noqa: BLE001 - surface OV errors cleanly
        raise BackendError(f"failed to load/compile model on {target_device}: {exc}") from exc
    load_time_ms = (time.perf_counter() - load_start) * 1000.0

    # Build deterministic zero inputs from the compiled model's inputs.
    # Dynamic dimensions are pinned to 1 (documented in reproducibility).
    np = _numpy()
    feed: dict[Any, Any] = {}
    for input_node in compiled.inputs:
        pshape = input_node.get_partial_shape()
        shape = [d.get_length() if d.is_static and d.get_length() > 0 else 1 for d in pshape]
        etype = str(input_node.get_element_type())
        dtype = np.float32
        if "i64" in etype:
            dtype = np.int64
        elif "i32" in etype:
            dtype = np.int32
        feed[input_node] = np.zeros(shape, dtype=dtype)
    first_input = next(iter(feed))

    def infer() -> None:
        compiled({first_input: feed[first_input]})

    sampler = TelemetrySampler(interval_seconds=0.5)
    latencies: list[float] = []
    try:
        sampler.start()
        for _ in range(config.warmup_runs):
            infer()
        for _ in range(config.iterations):
            start = time.perf_counter()
            infer()
            latencies.append((time.perf_counter() - start) * 1000.0)
    finally:
        sampler.stop()

    from .. import SCHEMA_VERSION
    from ..metrics import percentile, performance_per_watt

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
        "performance_per_watt": performance_per_watt(
            throughput_ips, telemetry["average_power_watts"]
        ),
        "throughput_inferences_per_second": round(throughput_ips, 2) if throughput_ips else None,
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": new_run_id("openvino"),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "system": system,
        "runtime": {
            "name": "openvino",
            "version": info.version,
            "backend": f"device:{target_device}",
            "device": config.device,
        },
        "model": {
            "name": Path(model_path).name,
            "format": "onnx",
            "quantization": None,
            "parameters": None,
            "checksum": None,
        },
        "metrics": metrics,
        "reproducibility": {
            "prompt": None,
            "max_tokens": None,
            "temperature": None,
            "seed": None,
            "context_length": None,
            "warmup_runs": config.warmup_runs,
            "iterations": config.iterations,
            "command": (
                f"aihwbench benchmark --runtime openvino --model-path {model_path} "
                f"--device {config.device}"
            ),
            "workload_type": "graph-inference",
        },
        "iterations": [
            {"iteration": i, "latency_ms": round(v, 2)} for i, v in enumerate(latencies)
        ],
    }
