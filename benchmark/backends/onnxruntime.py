"""ONNX Runtime backend — detection and benchmark scaffolding.

Detection uses a real import of the onnxruntime package and reports
available execution providers. Benchmark execution requires an ONNX
model plus provider-specific configuration and is reported as
CONFIGURATION_REQUIRED until a model pipeline is configured.
"""

from __future__ import annotations

from typing import Any

from .base import BackendError, BackendInfo, BenchmarkConfig, RuntimeStatus


def detect() -> BackendInfo:
    """Detect ONNX Runtime via package import."""
    try:
        import onnxruntime  # type: ignore[import-untyped]
    except ImportError:
        return BackendInfo(
            "onnxruntime", RuntimeStatus.NOT_INSTALLED, None,
            "pip install onnxruntime (CPU/DirectML) or onnxruntime-gpu (CUDA)",
        )
    providers = list(onnxruntime.get_available_providers())
    return BackendInfo(
        "onnxruntime",
        RuntimeStatus.AVAILABLE,
        str(getattr(onnxruntime, "__version__", None)),
        f"providers: {', '.join(providers)}",
    )


def run(config: BenchmarkConfig, system: dict[str, Any]) -> dict[str, Any]:
    """Benchmark an ONNX model. Requires model path + EP configuration."""
    info = detect()
    if info.status is not RuntimeStatus.AVAILABLE:
        raise BackendError(f"onnxruntime is not available: {info.status.value} ({info.detail})")
    raise BackendError(
        "ONNX Runtime benchmarking requires an ONNX model and execution-provider "
        "configuration. See docs/methodology.md for the planned v0.3 pipeline."
    )
