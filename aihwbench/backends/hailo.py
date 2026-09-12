"""Hailo HailoRT — an edge NPU, and the one backend that cannot take a model.

Hailo-8/8L/10H accelerators do not load ONNX or GGUF. They run `.hef` files:
graphs compiled ahead of time by the Dataflow Compiler for one specific device
architecture, with quantization and layer allocation already baked in. A Hailo-8
HEF will not run on a Hailo-10H, and neither will run anything else.

That constraint shapes everything here:

**There is no model zoo entry to fetch.** Every other backend in this project
can be pointed at a file somebody downloaded. This one needs a compilation step
on the user's side, so `run()` asks for a `.hef` and says what it is when one is
not supplied, rather than failing inside the driver.

**The numbers are inferences per second, not tokens.** These are vision and
audio accelerators; token metrics are reported as null rather than zero,
because zero would place a Hailo result on a tokens-per-second leaderboard at
the bottom instead of correctly excluding it.

**The HEF records its own target.** The compiled architecture is read out of
the file and recorded, so a result says `hailo8l` rather than `hailo`, and two
results compiled for different devices are not silently compared.

**Written, not observed.** No Hailo device has been available to this project.
The path targets HailoRT's `InferVStreams` API and has never run.
"""

from __future__ import annotations

import importlib.util
import time
from pathlib import Path
from typing import Any

from .base import BackendError, BackendInfo, BenchmarkConfig, RuntimeStatus, new_run_id, run_command


def _has_hailort() -> bool:
    try:
        return importlib.util.find_spec("hailo_platform") is not None
    except (ImportError, ValueError):  # pragma: no cover - malformed install
        return False


def detect() -> BackendInfo:
    """Detect HailoRT tooling, separating "no driver" from "no device"."""
    code, out = run_command(["hailortcli", "scan"], timeout=15.0)
    if code == 0 and out:
        first = out.splitlines()[0].strip() if out else ""
        # `scan` exits 0 with a "not found" line when the runtime is installed
        # and nothing is attached, which is a different problem from a missing
        # runtime and has a different fix.
        if "not found" in out.lower() or not first:
            return BackendInfo(
                "hailo",
                RuntimeStatus.HARDWARE_REQUIRED,
                None,
                "HailoRT is installed but no Hailo device was found. Check the "
                "M.2/PCIe card is seated and the hailo_pci driver is loaded.",
            )
        return BackendInfo("hailo", RuntimeStatus.AVAILABLE, None, first)

    if _has_hailort():
        return BackendInfo(
            "hailo",
            RuntimeStatus.HARDWARE_REQUIRED,
            None,
            "HailoRT Python package present but no accelerator detected",
        )
    return BackendInfo(
        "hailo",
        RuntimeStatus.HARDWARE_REQUIRED,
        None,
        "Requires Hailo-8/8L/10H hardware and HailoRT "
        "(https://hailo.ai/developer-zone/). Models must be compiled to .hef "
        "with the Dataflow Compiler; ONNX and GGUF will not load.",
    )


def hef_path(config: BenchmarkConfig) -> Path:
    """The compiled graph to run, or a refusal explaining what a HEF is."""
    raw = (config.extra or {}).get("model_path") or config.model
    if not raw:
        raise BackendError(
            "hailo needs a compiled graph: pass --model-path pointing at a .hef "
            "file. Hailo devices do not load ONNX or GGUF; a model must be "
            "compiled for the target architecture with Hailo's Dataflow "
            "Compiler first."
        )
    path = Path(str(raw))
    if path.suffix.lower() != ".hef":
        raise BackendError(
            f"{path.name} is not a .hef file. Hailo runs graphs compiled for a "
            "specific device architecture; other formats cannot be loaded."
        )
    if not path.is_file():
        raise BackendError(f"{path} does not exist")
    return path


def hef_architecture(hef: Any) -> str | None:
    """Which Hailo device this graph was compiled for.

    Worth recording because a HEF is not portable: one compiled for a Hailo-8
    will not run on a Hailo-10H, and two results from different targets are not
    comparable even when the source model was identical. Returns None when the
    field cannot be read rather than guessing a device.
    """
    for attribute in ("get_hef_device_arch", "get_device_arch"):
        reader = getattr(hef, attribute, None)
        if reader is None:
            continue
        try:
            value = reader()
        except Exception:  # noqa: BLE001 - metadata is a bonus, never a blocker
            continue
        if value is None:
            continue
        return getattr(value, "name", None) or str(value)
    return None


def run(config: BenchmarkConfig, system: dict[str, Any]) -> dict[str, Any]:
    """Benchmark a compiled HEF graph on a Hailo accelerator."""
    info = detect()
    if info.status is not RuntimeStatus.AVAILABLE:
        raise BackendError(f"hailo is not available: {info.status.value} ({info.detail})")

    model = hef_path(config)

    try:
        from hailo_platform import (
            HEF,
            ConfigureParams,
            FormatType,
            HailoStreamInterface,
            InferVStreams,
            InputVStreamParams,
            OutputVStreamParams,
            VDevice,
        )
    except ImportError as exc:
        raise BackendError(
            f"hailo_platform is not importable ({exc}). Install HailoRT and its "
            "Python bindings from https://hailo.ai/developer-zone/"
        ) from exc

    import numpy as np

    from ..metrics import percentile, performance_per_watt
    from ..telemetry import TelemetrySampler
    from ..versions import CURRENT_SCHEMA_VERSION
    from .base import file_sha256

    load_start = time.perf_counter()
    try:
        hef = HEF(str(model))
        device = VDevice()
        configure_params = ConfigureParams.create_from_hef(hef, interface=HailoStreamInterface.PCIe)
        network_group = device.configure(hef, configure_params)[0]
        network_params = network_group.create_params()
        input_params = InputVStreamParams.make(network_group, format_type=FormatType.FLOAT32)
        output_params = OutputVStreamParams.make(network_group, format_type=FormatType.FLOAT32)
        input_infos = hef.get_input_vstream_infos()
    except Exception as exc:  # noqa: BLE001 - surface driver errors cleanly
        raise BackendError(f"failed to configure {model.name} on the Hailo device: {exc}") from exc
    load_time_ms = (time.perf_counter() - load_start) * 1000.0

    # Deterministic zero inputs, one batch, for every declared stream. Feeding
    # only the first would mis-measure a multi-input graph, the same mistake
    # the ONNX backend documents.
    feed = {
        info_.name: np.zeros((1, *tuple(info_.shape)), dtype=np.float32) for info_ in input_infos
    }

    architecture = hef_architecture(hef)
    sampler = TelemetrySampler(interval_seconds=0.5)
    sampler.start()
    latencies: list[float] = []
    try:
        with network_group.activate(network_params):
            with InferVStreams(network_group, input_params, output_params) as pipeline:
                for _ in range(config.warmup_runs):
                    pipeline.infer(feed)
                for _ in range(config.iterations):
                    start = time.perf_counter()
                    pipeline.infer(feed)
                    latencies.append((time.perf_counter() - start) * 1000.0)
    except Exception as exc:  # noqa: BLE001 - surface driver errors cleanly
        raise BackendError(f"inference failed on the Hailo device: {exc}") from exc
    finally:
        sampler.stop()
        try:
            device.release()
        except Exception:  # noqa: BLE001 - best-effort teardown
            pass

    telemetry = sampler.summary()
    mean_latency = sum(latencies) / len(latencies) if latencies else None
    throughput = (1000.0 / mean_latency) if mean_latency else None

    metrics: dict[str, Any] = {
        "load_time_ms": round(load_time_ms, 2),
        # Null, not zero. These are vision and audio accelerators; a zero here
        # would rank a Hailo result last on a tokens-per-second leaderboard
        # instead of correctly leaving it off one.
        "ttft_ms": None,
        "prompt_tokens_per_second": None,
        "generation_tokens_per_second": None,
        "total_latency_ms": round(mean_latency, 2) if mean_latency else None,
        "p50_latency_ms": (round(v, 2) if (v := percentile(latencies, 50)) is not None else None),
        "p95_latency_ms": (round(v, 2) if (v := percentile(latencies, 95)) is not None else None),
        "throughput_inferences_per_second": round(throughput, 2) if throughput else None,
        "performance_per_watt": performance_per_watt(
            throughput, telemetry.get("average_power_watts")
        ),
    }
    metrics.update(telemetry)

    return {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "run_id": new_run_id("hailo"),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "system": system,
        "runtime": {
            "name": "hailo",
            "version": info.version,
            "backend": "hailort-infer-vstreams",
            # The architecture the graph was compiled for, when the file says.
            # A Hailo-8 result and a Hailo-10H result are different hardware
            # and must not share a device label.
            "device": architecture.lower() if architecture else "hailo",
            "device_requested": config.device,
        },
        "model": {
            "name": model.name,
            "format": "hef",
            # Quantization is chosen at compile time and baked in; the HEF does
            # not expose it in a form worth asserting, so it stays unknown
            # rather than being guessed from a filename.
            "quantization": None,
            "parameters": None,
            "checksum": file_sha256(str(model)),
            "compiled_for": architecture,
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
            "command": f"aihwbench benchmark --runtime hailo --model-path {model}",
            "workload_type": "graph-inference",
            "graph_inputs": [
                {"name": info_.name, "shape": list(info_.shape)} for info_ in input_infos
            ],
        },
        "iterations": [
            {"iteration": i, "latency_ms": round(v, 2), "total_latency_ms": round(v, 2)}
            for i, v in enumerate(latencies, start=1)
        ],
    }


# Declared capability contract: truthful hardware/library prerequisites.
# Detection never reports availability when these are missing.
CAPABILITIES: tuple[str, ...] = (
    "hailo-npu-required",
    "hailort-required",
    "edge-device-only",
    "precompiled-hef-required",
    "graph-inference-not-tokens",
)
