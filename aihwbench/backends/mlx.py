"""Apple MLX backend — detection only outside Apple Silicon.

MLX is Apple's array framework for Apple Silicon. Benchmarking requires
macOS on M-series hardware with the optional ``mlx-lm`` package installed.
Detection reports honestly; run() refuses to fabricate results elsewhere.
"""

from __future__ import annotations

import platform
import sys
from typing import Any

from .base import BackendError, BackendInfo, BenchmarkConfig, RuntimeStatus, run_command


def detect() -> BackendInfo:
    """Detect MLX availability (Apple Silicon + mlx-lm package)."""
    if platform.system() != "Darwin":
        return BackendInfo(
            "mlx",
            RuntimeStatus.HARDWARE_REQUIRED,
            None,
            "Requires a Mac with Apple Silicon (M1/M2/M3/M4); see https://github.com/ml-explore/mlx",
        )
    if platform.machine() != "arm64":
        return BackendInfo(
            "mlx",
            RuntimeStatus.HARDWARE_REQUIRED,
            None,
            "MLX requires Apple Silicon (arm64); Intel Macs are not supported",
        )
    code, _out = run_command([sys.executable, "-c", "import mlx.core"], timeout=30.0)
    if code == 0:
        return BackendInfo("mlx", RuntimeStatus.AVAILABLE, None, "mlx core importable")
    return BackendInfo(
        "mlx",
        RuntimeStatus.CONFIGURATION_REQUIRED,
        None,
        "Install the MLX Python stack: pip install mlx-lm",
    )


def run(config: BenchmarkConfig, system: dict[str, Any]) -> dict[str, Any]:
    """MLX benchmarking is planned for a future release."""
    info = detect()
    if info.status is not RuntimeStatus.AVAILABLE:
        raise BackendError(f"mlx is not available: {info.status.value} ({info.detail})")
    raise BackendError("MLX benchmarking is planned for a future release. See ROADMAP.md.")
