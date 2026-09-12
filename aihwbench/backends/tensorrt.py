"""NVIDIA TensorRT — measured through ONNX Runtime's TensorRT provider.

The obstacle with TensorRT has never been the API, it is that an engine is
built for one GPU, one driver and one precision, and is not portable to
another machine. That is why no engine is committed here and why a TensorRT
number cannot be shipped the way a GGUF result can.

ONNX Runtime's TensorRT execution provider removes the part that blocks
measurement: it takes an ordinary ONNX model, builds the engine on the machine
doing the benchmarking, caches it, and runs it. The first run therefore
includes engine construction and can take minutes — that is a real cost of
this runtime and is reported as load time rather than hidden by a warm-up.

**TensorRT-LLM is a different thing and is not this.** It is a separate
engine-compilation stack for transformer models, officially Linux, and it
would need its own backend. This one measures ONNX graphs.

Verified on the reference machine only insofar as the delegation path is: the
identical code runs DirectML here, where 101 of 104 MobileNetV2 nodes were
assigned to the accelerator. The TensorRT provider itself is not installed,
so this specific path is written and not observed.
"""

from __future__ import annotations

from typing import Any

from ._delegate import run_via_onnxruntime
from .base import (
    BackendError,
    BackendInfo,
    BenchmarkConfig,
    RuntimeStatus,
    run_command,
    which,
)


def detect() -> BackendInfo:
    """Detect TensorRT tooling."""
    trtexec = which("trtexec")
    if trtexec:
        code, out = run_command([trtexec, "--help"], timeout=15.0)
        version = None
        if code == 0 and out:
            for line in out.splitlines():
                if "TensorRT" in line:
                    version = line.strip()
                    break
        return BackendInfo(
            "tensorrt",
            RuntimeStatus.CONFIGURATION_REQUIRED,
            version,
            "trtexec found; requires per-GPU engine builds to benchmark",
        )
    try:
        import tensorrt

        return BackendInfo(
            "tensorrt",
            RuntimeStatus.CONFIGURATION_REQUIRED,
            str(getattr(tensorrt, "__version__", None)),
            "Python package found; requires per-GPU engine builds to benchmark",
        )
    except ImportError:
        pass
    return BackendInfo(
        "tensorrt",
        RuntimeStatus.NOT_INSTALLED,
        None,
        "Install TensorRT from https://developer.nvidia.com/tensorrt (requires NVIDIA GPU + CUDA)",
    )


def _has_tensorrt_provider() -> bool:
    """Whether ONNX Runtime here can build and run a TensorRT engine."""
    try:
        import onnxruntime

        return "TensorrtExecutionProvider" in onnxruntime.get_available_providers()
    except Exception:  # noqa: BLE001 - detection must never raise
        return False


def run(config: BenchmarkConfig, system: dict[str, Any]) -> dict[str, Any]:
    """Benchmark an ONNX model on a TensorRT engine built for this GPU.

    The engine build happens inside the session creation ONNX Runtime does, so
    it lands in `load_time_ms`. On a first run for a given model and GPU that
    figure is minutes rather than milliseconds, and it belongs in the result:
    a runtime that needs ten minutes before it answers anything is making a
    trade a reader should be able to see.
    """
    if not _has_tensorrt_provider():
        info = detect()
        raise BackendError(
            "tensorrt: ONNX Runtime has no TensorrtExecutionProvider, so there "
            "is no way to build or run an engine here. Install onnxruntime-gpu "
            "built against TensorRT on a machine with an NVIDIA GPU. "
            f"(detection: {info.status.value} — {info.detail})"
        )
    return run_via_onnxruntime(
        config,
        system,
        name="tensorrt",
        device="tensorrt",
        backend="onnxruntime-tensorrt",
    )


# Declared capability contract: truthful hardware/library prerequisites.
# Detection never reports availability when these are missing.
CAPABILITIES: tuple[str, ...] = (
    "nvidia-gpu-required",
    "tensorrt-libs-required",
    "engine-build-required",
    "fp16-int8",
)
