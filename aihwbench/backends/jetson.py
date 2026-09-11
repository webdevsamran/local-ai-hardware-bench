"""Jetson backend — NVIDIA's embedded boards, where the usual numbers mislead.

A Jetson is not a small desktop GPU. Three differences change what a benchmark
must record, and a harness that treats it as "a slow RTX card" produces numbers
nobody can reproduce:

**Memory is unified.** CPU and GPU share one pool, so VRAM is not a separate
budget and a model that fits does so at the system's expense. A `gpu_vram_mb`
copied from the discrete-GPU path is a category error here.

**Performance is a mode, not a property.** `nvpmodel` selects a power envelope
— 10 W, 15 W, 25 W, MAXN — and throughput changes severalfold between them. Two
Jetson results without the mode recorded are not comparable, and the gap will
be read as a hardware or software difference.

**Clocks are not boosted by default.** `jetson_clocks` pins them to maximum;
without it the board ramps and a short benchmark measures the ramp. Same trap
that made short generative runs useless on the reference laptop, with a larger
amplitude.

Detection reads the board model and the power mode, so a result is
attributable. This machine is x86_64 and says so.
"""

from __future__ import annotations

import platform
from pathlib import Path
from typing import Any

from .base import BackendError, BackendInfo, BenchmarkConfig, RuntimeStatus, run_command

#: L4T writes the board release here; its presence is the reliable marker.
_TEGRA_RELEASE = Path("/etc/nv_tegra_release")

#: Device-tree model, e.g. "NVIDIA Jetson Orin Nano Developer Kit".
_DEVICE_TREE_MODEL = Path("/proc/device-tree/model")


def board_model() -> str | None:
    """The board's own name, or None on anything that is not a Jetson."""
    try:
        if _DEVICE_TREE_MODEL.is_file():
            raw = _DEVICE_TREE_MODEL.read_text(encoding="utf-8", errors="replace")
            # The device tree null-terminates its strings.
            model = raw.replace(chr(0), "").strip()
            if "jetson" in model.lower() or "tegra" in model.lower():
                return model
    except OSError:  # pragma: no cover - platform dependent
        pass
    return None


def power_mode() -> str | None:
    """The active `nvpmodel` mode, which sets the power envelope.

    Recorded because throughput changes severalfold across modes: two results
    without it are not comparable, and the difference looks like something
    else entirely.
    """
    code, out = run_command(["nvpmodel", "-q"], timeout=20.0)
    if code != 0 or not out:
        return None
    return " ".join(out.split())


def detect() -> BackendInfo:
    if platform.machine().lower() not in ("aarch64", "arm64"):
        return BackendInfo(
            "jetson",
            RuntimeStatus.HARDWARE_REQUIRED,
            None,
            f"Not an ARM64 machine (this is {platform.machine()}). Jetson boards are aarch64.",
        )
    model = board_model()
    if not model and not _TEGRA_RELEASE.is_file():
        return BackendInfo(
            "jetson",
            RuntimeStatus.HARDWARE_REQUIRED,
            None,
            "ARM64, but no Tegra marker found: this is an ARM machine that is "
            "not a Jetson. Try the `arm_sbc` backend.",
        )

    mode = power_mode()
    detail = model or "Jetson (L4T detected)"
    if mode:
        detail = f"{detail}; nvpmodel: {mode}"
    else:
        detail = (
            f"{detail}; nvpmodel could not be read, so the power envelope is "
            "unknown and results will not be comparable across modes"
        )
    return BackendInfo("jetson", RuntimeStatus.AVAILABLE, None, detail)


def run(config: BenchmarkConfig, system: dict[str, Any]) -> dict[str, Any]:
    """Benchmark on a Jetson through llama.cpp, recording the power mode.

    Refuses when the mode cannot be read. A Jetson result whose envelope is
    unknown cannot be compared with another Jetson result, and publishing one
    invites exactly that comparison.
    """
    info = detect()
    if info.status is not RuntimeStatus.AVAILABLE:
        raise BackendError(f"jetson is not available: {info.status.value} ({info.detail})")

    mode = power_mode()
    if not mode:
        raise BackendError(
            "the nvpmodel power mode could not be read. Throughput changes "
            "severalfold between Jetson power modes, so a result without it "
            "recorded is not comparable with any other Jetson result."
        )

    from . import llama_cpp

    result = llama_cpp.run(config, system)
    result["runtime"]["name"] = "jetson"
    result["runtime"]["backend"] = "llama.cpp-jetson"
    result.setdefault("reproducibility", {})["power_profile"] = mode
    # Unified memory: a discrete-GPU VRAM figure would be a category error.
    result.setdefault("system", {})["memory_is_unified"] = True
    return result


#: Declared capability contract: truthful prerequisites and quirks.
CAPABILITIES: tuple[str, ...] = (
    "aarch64-required",
    "tegra-required",
    "unified-memory",
    "power-mode-must-be-recorded",
    "clocks-not-boosted-by-default",
)
