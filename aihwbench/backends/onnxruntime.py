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
    resolved_device,
)


def detect() -> BackendInfo:
    """Detect ONNX Runtime via package import."""
    try:
        import onnxruntime
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


#: This project's device vocabulary, mapped to the ONNX Runtime execution
#: provider that implements it.
#:
#: These are the accelerators the project's own backends delegate here for:
#: `qnn` is how a Snapdragon X NPU is reached, `tensorrt` how an NVIDIA engine
#: is, `dml` how Windows ML reaches any DirectX 12 device, `rocm`/`migraphx`
#: how an AMD card is on Linux, `openvino` and `coreml` likewise. Each is a
#: provider of the same runtime rather than a separate engine, which is why
#: those backends delegate instead of growing their own benchmark loop.
_PROVIDER_FOR_DEVICE: dict[str, str] = {
    "cuda": "CUDAExecutionProvider",
    "dml": "DmlExecutionProvider",
    "qnn": "QNNExecutionProvider",
    "tensorrt": "TensorrtExecutionProvider",
    "rocm": "ROCMExecutionProvider",
    "migraphx": "MIGraphXExecutionProvider",
    "openvino": "OpenVINOExecutionProvider",
    "coreml": "CoreMLExecutionProvider",
    "nnapi": "NnapiExecutionProvider",
    "webgpu": "WebGpuExecutionProvider",
}


def _providers_for_device(device: str) -> list[str] | None:
    """Map a device hint to an execution-provider preference order.

    The CPU provider is appended as a *fallback for unsupported operators*,
    not as a fallback for a missing accelerator: ONNX Runtime partitions a
    graph across providers, and a node the NPU cannot run has to go somewhere.
    A provider that failed to initialise entirely is a different matter and is
    caught in `run()`, which refuses when the requested provider is absent
    from the session's active list — otherwise a CPU measurement would be
    published under an accelerator's name.
    """
    available = _available_providers()
    if device == "cpu":
        return ["CPUExecutionProvider"]
    if device == "auto":
        return None  # let ORT pick its default priority order

    provider = _PROVIDER_FOR_DEVICE.get(device)
    if provider is not None and provider in available:
        return [provider, "CPUExecutionProvider"]

    known = ", ".join(sorted(_PROVIDER_FOR_DEVICE) + ["cpu", "auto"])
    if provider is None:
        raise BackendError(f"unknown device {device!r}; this backend understands: {known}")
    raise BackendError(
        f"device {device!r} needs {provider}, which this ONNX Runtime build "
        f"does not have (installed providers: {', '.join(available)}). "
        f"Install the matching package — for example onnxruntime-qnn for qnn, "
        "onnxruntime-gpu for cuda and tensorrt — rather than running on the "
        "CPU under an accelerator's name."
    )


def _available_providers() -> list[str]:
    import onnxruntime

    return list(onnxruntime.get_available_providers())


def node_assignment(model_path: str, providers: list[str]) -> dict[str, int] | None:
    """How many graph nodes each execution provider actually ran.

    "Did the provider load?" is the question everyone asks and it is the wrong
    one. ONNX Runtime partitions a graph: a provider can initialise, report
    itself active, and be given almost none of the model. The QNN provider does
    exactly this with a float32 model — it wants quantized QDQ operators, takes
    a handful of nodes or none, and leaves the rest to the CPU. Every
    presence check says the NPU is running; a CPU does the work.

    So this counts assignments rather than trusting membership, by running one
    inference with profiling on and reading the per-node provider out of the
    trace ONNX Runtime writes.

    It uses a throwaway session: profiling adds bookkeeping to every node, and
    measuring with it enabled would report the cost of the instrumentation as
    the cost of the model. One extra model load, outside the timed loop.

    **The session must be released before another one is opened**, which is why
    the caller runs this before creating the measurement session and why the
    session is deleted here rather than left to the garbage collector. Two
    concurrent DirectML sessions on one model segfault the process — verified
    on the reference machine, exit 139, no Python traceback. Sequential
    sessions are fine, so the ordering is the entire fix. A crash rather than
    an exception is also why this cannot be papered over with `try`.

    Returns None when the trace cannot be produced or parsed — unknown, which
    the caller must not read as zero.
    """
    import json
    import os

    import onnxruntime

    profile_path: str | None = None
    session: Any = None
    try:
        options = onnxruntime.SessionOptions()
        options.enable_profiling = True
        session = onnxruntime.InferenceSession(
            str(model_path), sess_options=options, providers=providers
        )
        session.run([o.name for o in session.get_outputs()], _make_inputs(session))
        profile_path = session.end_profiling()
        # Before any other session exists, and before reading the file.
        del session
        session = None
        if not profile_path or not os.path.isfile(profile_path):
            return None
        with open(profile_path, encoding="utf-8") as handle:
            events = json.load(handle)
    except Exception:  # noqa: BLE001 - a probe must never fail the benchmark
        return None
    finally:
        del session
        if profile_path and os.path.isfile(profile_path):
            try:
                os.remove(profile_path)
            except OSError:
                pass

    counts: dict[str, int] = {}
    for event in events if isinstance(events, list) else []:
        if not isinstance(event, dict) or event.get("cat") != "Node":
            continue
        args = event.get("args")
        if not isinstance(args, dict):
            continue
        provider = args.get("provider")
        if isinstance(provider, str) and provider:
            counts[provider] = counts.get(provider, 0) + 1
    return counts or None


def _numpy() -> Any:
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

    import onnxruntime

    providers = _providers_for_device(config.device)

    # Before the measurement session exists, and deliberately so: two
    # concurrent DirectML sessions on one model segfault the process, and this
    # probe opens one of its own. Sequential is safe; overlapping is not.
    #
    # Loading is not running. An accelerator provider can initialise, report
    # itself active, and be handed none of the graph -- which is how a CPU
    # measurement comes to be published under an NPU's name. Ask what it
    # actually ran before spending any time measuring it.
    assignment: dict[str, int] | None = None
    if config.device not in ("cpu", "auto"):
        assignment = node_assignment(str(model_path), providers or [])
        if assignment is not None and providers:
            if assignment.get(providers[0], 0) == 0:
                where = ", ".join(f"{k}={v}" for k, v in sorted(assignment.items()))
                raise BackendError(
                    f"{providers[0]} loaded but was assigned no nodes of this "
                    f"model ({where}). The measurement would describe the CPU "
                    f"under the name {config.device!r}. This usually means the "
                    "model is not in a form the accelerator accepts -- QNN and "
                    "most NPU providers need a quantized QDQ graph, not float32."
                )

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
            # The provider that actually ran, not the flag that was typed.
            # `active_providers` is ordered by preference, so the first is the
            # one ONNX Runtime chose.
            "device": (
                resolved_device(active_providers[0] if active_providers else None) or config.device
            ),
            "device_requested": config.device,
            # How much of the graph the accelerator actually took. Provider
            # membership says a provider is present; this says it ran
            # something, which is the claim a result implicitly makes.
            "node_assignment": assignment,
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
            {
                "iteration": i,
                # Both names, on purpose. `total_latency_ms` is the canonical
                # one every consumer reads; `latency_ms` is what this backend
                # has always written and what the published results carry.
                # Emitting only the second meant the data-quality gate found
                # no series here and reported its variance check as passing
                # without running -- and the graph runtimes turned out to be
                # the noisiest results in the corpus.
                "latency_ms": round(v, 2),
                "total_latency_ms": round(v, 2),
            }
            for i, v in enumerate(latencies)
        ],
    }
