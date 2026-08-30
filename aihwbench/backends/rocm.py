"""AMD ROCm backend — detection only.

ROCm on Windows is limited to HIP SDK; full ROCm runtime benchmarking
currently requires Linux. Detection checks for ROCm/HIP tooling and
reports honestly.
"""

from __future__ import annotations

import platform
from typing import Any

from .base import BackendError, BackendInfo, BenchmarkConfig, RuntimeStatus, run_command


def detect() -> BackendInfo:
    """Detect ROCm / HIP tooling."""
    if platform.system() == "Windows":
        code, out = run_command(["hipInfo"], timeout=10.0)
        if code == 0 and out:
            return BackendInfo(
                "rocm",
                RuntimeStatus.CONFIGURATION_REQUIRED,
                None,
                "HIP SDK present; full ROCm LLM benchmarking requires Linux",
            )
        return BackendInfo(
            "rocm",
            RuntimeStatus.HARDWARE_REQUIRED,
            None,
            "Requires an AMD Radeon GPU with ROCm support (Linux recommended)",
        )
    for tool in ("rocminfo", "hipconfig"):
        code, out = run_command([tool], timeout=10.0)
        if code == 0 and out:
            return BackendInfo("rocm", RuntimeStatus.AVAILABLE, None, out.splitlines()[0])
    return BackendInfo(
        "rocm",
        RuntimeStatus.HARDWARE_REQUIRED,
        None,
        "Install ROCm from https://rocm.docs.amd.com (requires supported AMD GPU)",
    )


def run(config: BenchmarkConfig, system: dict[str, Any]) -> dict[str, Any]:
    """ROCm benchmarking is planned for v0.5."""
    info = detect()
    if info.status is not RuntimeStatus.AVAILABLE:
        raise BackendError(f"rocm is not available: {info.status.value} ({info.detail})")
    raise BackendError("ROCm benchmarking is planned for v0.5. See ROADMAP.md.")


# Declared capability contract: truthful hardware/library prerequisites.
# Detection never reports availability when these are missing.
CAPABILITIES: tuple[str, ...] = (
    "amd-gpu-required",
    "hip-runtime-required",
    "linux-primary",
)
