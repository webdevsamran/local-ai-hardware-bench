"""Hailo HailoRT backend — detection only.

Hailo accelerators (Hailo-8/8L/10H) require HailoRT plus PCIe/M.2 or
USB attached hardware. Detection checks for hailortcli and the HailoRT
Python package.
"""

from __future__ import annotations

import platform
from typing import Any

from .base import BackendError, BackendInfo, BenchmarkConfig, RuntimeStatus, run_command


def detect() -> BackendInfo:
    """Detect HailoRT tooling."""
    code, out = run_command(["hailortcli", "scan"], timeout=15.0)
    if code == 0 and out:
        detail = out.splitlines()[0] if out else None
        return BackendInfo("hailo", RuntimeStatus.AVAILABLE, None, detail)
    try:
        import importlib.util

        if importlib.util.find_spec("hailo_platform") is None:
            raise ImportError
        return BackendInfo(
            "hailo",
            RuntimeStatus.HARDWARE_REQUIRED,
            None,
            "HailoRT python package present but no accelerator detected",
        )
    except ImportError:
        pass
    note = "" if platform.system() == "Windows" else ""
    return BackendInfo(
        "hailo",
        RuntimeStatus.HARDWARE_REQUIRED,
        None,
        ("Requires Hailo-8/8L/10H hardware and HailoRT. " + note).strip(),
    )


def run(config: BenchmarkConfig, system: dict[str, Any]) -> dict[str, Any]:
    """Hailo benchmarking is planned for v0.8."""
    info = detect()
    if info.status is not RuntimeStatus.AVAILABLE:
        raise BackendError(f"hailo is not available: {info.status.value} ({info.detail})")
    raise BackendError("Hailo benchmarking is planned for v0.8. See ROADMAP.md.")


# Declared capability contract: truthful hardware/library prerequisites.
# Detection never reports availability when these are missing.
CAPABILITIES: tuple[str, ...] = (
    "hailo-npu-required",
    "hailort-required",
    "edge-device-only",
)
