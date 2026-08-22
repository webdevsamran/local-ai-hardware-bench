"""NVIDIA TensorRT / TensorRT-LLM backend — detection only.

Detection looks for trtexec on PATH and the tensorrt Python package.
Benchmarking requires engine builds specific to each GPU, which are not
committed to this repository.
"""

from __future__ import annotations

from typing import Any

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
        import tensorrt  # type: ignore[import-not-found,import-untyped]

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


def run(config: BenchmarkConfig, system: dict[str, Any]) -> dict[str, Any]:
    """TensorRT benchmarking is planned for v0.6."""
    info = detect()
    if info.status is not RuntimeStatus.CONFIGURATION_REQUIRED:
        raise BackendError(f"tensorrt is not available: {info.status.value} ({info.detail})")
    raise BackendError("TensorRT benchmarking is planned for v0.6. See ROADMAP.md.")
