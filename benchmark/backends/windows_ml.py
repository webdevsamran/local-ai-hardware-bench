"""Microsoft Windows ML / DirectML backend — detection only.

Windows ML ships with Windows 10 1809+ as an OS component; usable
benchmarking requires an ONNX model plus a DirectML/CPU device choice.
"""

from __future__ import annotations

import platform
from typing import Any

from .base import BackendError, BackendInfo, BenchmarkConfig, RuntimeStatus


def detect() -> BackendInfo:
    """Detect Windows ML availability by OS version."""
    if platform.system() != "Windows":
        return BackendInfo(
            "windows_ml", RuntimeStatus.UNSUPPORTED_PLATFORM, None,
            "Windows ML is only available on Windows",
        )
    build = int(platform.version().split(".")[2]) if platform.version().count(".") >= 2 else 0
    if build >= 17763:  # 1809 introduced Windows ML
        return BackendInfo(
            "windows_ml", RuntimeStatus.CONFIGURATION_REQUIRED, f"build {build}",
            "OS component present; requires an ONNX model pipeline to benchmark",
        )
    return BackendInfo(
        "windows_ml", RuntimeStatus.NOT_AVAILABLE, f"build {build}",
        "Windows 10 1809+ required",
    )


def run(config: BenchmarkConfig, system: dict[str, Any]) -> dict[str, Any]:
    """Windows ML benchmarking is planned alongside ONNX Runtime work."""
    info = detect()
    if info.status is not RuntimeStatus.CONFIGURATION_REQUIRED:
        raise BackendError(f"windows_ml is not available: {info.status.value} ({info.detail})")
    raise BackendError("Windows ML benchmarking is planned. See ROADMAP.md.")