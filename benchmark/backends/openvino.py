"""Intel OpenVINO backend — detection only (v0.4 milestone).

Detection imports the openvino package and reports available devices
(CPU, GPU, NPU). Benchmarking requires OpenVINO IR/GenAI models and is
reported as CONFIGURATION_REQUIRED until configured.
"""

from __future__ import annotations

from typing import Any

from .base import BackendError, BackendInfo, BenchmarkConfig, RuntimeStatus


def detect() -> BackendInfo:
    """Detect OpenVINO via package import."""
    try:
        import openvino  # type: ignore[import-untyped]
    except ImportError:
        return BackendInfo(
            "openvino", RuntimeStatus.NOT_INSTALLED, None,
            "pip install openvino; Intel NPU benchmarking additionally needs "
            "an Intel Core Ultra class CPU with the NPU driver installed",
        )
    try:
        core = openvino.Core()
        devices = [d for d in core.get_available_devices()]
    except Exception:  # noqa: BLE001 - any runtime failure means unusable
        devices = []
    detail = f"devices: {', '.join(devices)}" if devices else "no devices enumerated"
    return BackendInfo(
        "openvino",
        RuntimeStatus.AVAILABLE,
        str(getattr(openvino, "__version__", None)),
        detail,
    )


def run(config: BenchmarkConfig, system: dict[str, Any]) -> dict[str, Any]:
    """Benchmark an OpenVINO model. Not implemented until v0.4."""
    info = detect()
    if info.status is not RuntimeStatus.AVAILABLE:
        raise BackendError(f"openvino is not available: {info.status.value} ({info.detail})")
    raise BackendError(
        "OpenVINO benchmarking is planned for v0.4. See ROADMAP.md."
    )
