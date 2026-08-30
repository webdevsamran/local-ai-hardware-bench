"""Qualcomm QNN backend — detection only.

Detection checks for the Qualcomm AI Engine Direct (QNN) SDK via the
QNN_SDK_ROOT environment variable and common install paths. Real QNN
benchmarking additionally requires Snapdragon X hardware or an NPU
device and compiled QNN context binaries.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .base import BackendError, BackendInfo, BenchmarkConfig, RuntimeStatus

_COMMON_SDK_PATHS = [
    Path("C:/Qualcomm/AIStack"),
    Path(os.path.expanduser("~")) / "Qualcomm" / "AIStack",
]


def detect() -> BackendInfo:
    """Detect Qualcomm QNN SDK."""
    sdk_root = os.environ.get("QNN_SDK_ROOT")
    candidates = [Path(sdk_root)] if sdk_root else []
    candidates += _COMMON_SDK_PATHS
    for candidate in candidates:
        if candidate.is_dir():
            return BackendInfo(
                "qnn",
                RuntimeStatus.CONFIGURATION_REQUIRED,
                None,
                f"SDK found at {candidate}; requires Snapdragon NPU hardware "
                "and compiled context binaries to benchmark",
            )
    return BackendInfo(
        "qnn",
        RuntimeStatus.HARDWARE_REQUIRED,
        None,
        "Requires Qualcomm Snapdragon X (or Hexagon NPU) hardware and the "
        "Qualcomm AI Engine Direct SDK",
    )


def run(config: BenchmarkConfig, system: dict[str, Any]) -> dict[str, Any]:
    """QNN benchmarking is planned for v0.7."""
    info = detect()
    if info.status is not RuntimeStatus.CONFIGURATION_REQUIRED:
        raise BackendError(f"qnn is not available: {info.status.value} ({info.detail})")
    raise BackendError("QNN benchmarking is planned for v0.7. See ROADMAP.md.")


# Declared capability contract: truthful hardware/library prerequisites.
# Detection never reports availability when these are missing.
CAPABILITIES: tuple[str, ...] = (
    "qualcomm-soc-required",
    "qnn-libs-required",
    "context-binary-required",
)
