"""SYCL backend — Intel GPUs, which most of this project's readers already own.

Nearly every recent Intel laptop has an Iris Xe or Arc integrated GPU sitting
idle while the CPU does the inference. SYCL through oneAPI is how llama.cpp
uses it, and the reason it is worth a backend is that the alternative on those
machines is not a faster GPU -- it is no GPU at all.

Detection separates the same two questions Vulkan does, because the answers
differ and only one of them is actionable:

**Is there an Intel GPU?** Read from the platform rather than assumed from the
CPU vendor: an Intel CPU does not imply a usable Intel GPU, and a machine with
a discrete card may have the integrated one disabled in firmware.

**Is there a oneAPI runtime and a SYCL-enabled build?** `sycl-ls` lists the
devices oneAPI can reach. Without it, an Intel GPU is present and unusable,
and saying so beats reporting the backend as unsupported.

The reference machine is the interesting case: an Iris Xe is present and
Vulkan can see it, but there is no oneAPI and the llama.cpp build is CUDA-only.
The hardware is not the limitation, and the report says which half is.
"""

from __future__ import annotations

import platform
from pathlib import Path
from typing import Any

from ._delegate import run_via_llama_cpp
from .base import (
    BackendError,
    BackendInfo,
    BenchmarkConfig,
    RuntimeStatus,
    run_command,
)


def intel_gpus() -> list[str]:
    """Intel GPUs the operating system reports, by name."""
    if platform.system() == "Windows":
        code, out = run_command(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-CimInstance Win32_VideoController | "
                "Where-Object { $_.Name -like '*Intel*' } | "
                "Select-Object -ExpandProperty Name",
            ],
            timeout=45.0,
        )
        if code == 0 and out:
            return [line.strip() for line in out.splitlines() if line.strip()]
        return []

    # Linux: the render nodes' vendor id. 0x8086 is Intel.
    names: list[str] = []
    for vendor_file in sorted(Path("/sys/class/drm").glob("card*/device/vendor")):
        try:
            if vendor_file.read_text(encoding="utf-8").strip().lower() == "0x8086":
                names.append(vendor_file.parent.name)
        except OSError:  # pragma: no cover - platform dependent
            continue
    return names


def sycl_devices() -> list[str]:
    """Devices oneAPI can reach, or an empty list if `sycl-ls` is absent."""
    code, out = run_command(["sycl-ls"], timeout=30.0)
    if code != 0 or not out:
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]


def build_has_sycl_backend() -> bool | None:
    """Whether the located llama.cpp ships a SYCL backend."""
    from .llama_cpp import _find_binary

    server = _find_binary("llama-server")
    if not server:
        return None
    directory = Path(server).parent
    if any(directory.glob("ggml-sycl*")):
        return True
    code, out = run_command([server, "--list-devices"], timeout=60.0)
    if code == 0 and out and "sycl" in out.lower():
        return True
    return False


def detect() -> BackendInfo:
    gpus = intel_gpus()
    devices = sycl_devices()
    has_backend = build_has_sycl_backend()

    if not gpus and not devices:
        return BackendInfo(
            "sycl",
            RuntimeStatus.HARDWARE_REQUIRED,
            None,
            "No Intel GPU found. SYCL targets Intel integrated and Arc GPUs.",
        )
    listed = ", ".join(gpus) or "an Intel GPU"

    if not devices:
        return BackendInfo(
            "sycl",
            RuntimeStatus.CONFIGURATION_REQUIRED,
            None,
            f"{listed} is present but oneAPI is not installed, so nothing can "
            "reach it. Install the Intel oneAPI Base Toolkit; `sycl-ls` should "
            "then list the device.",
        )
    if has_backend is None:
        return BackendInfo(
            "sycl",
            RuntimeStatus.NOT_INSTALLED,
            None,
            f"oneAPI can reach {listed}, but no llama.cpp was found to use it.",
        )
    if not has_backend:
        return BackendInfo(
            "sycl",
            RuntimeStatus.CONFIGURATION_REQUIRED,
            None,
            f"oneAPI can reach {listed}, but this llama.cpp build has no SYCL "
            "backend. Rebuild with -DGGML_SYCL=ON. The hardware is not the "
            "limitation.",
        )
    return BackendInfo("sycl", RuntimeStatus.AVAILABLE, None, f"SYCL devices: {len(devices)}")


def run(config: BenchmarkConfig, system: dict[str, Any]) -> dict[str, Any]:
    """Benchmark through llama.cpp's SYCL backend.

    Refuses rather than falling back to CPU. A result labelled `sycl` that ran
    on the CPU would understate Intel GPUs everywhere it was read, and nothing
    downstream could detect the mislabelling.
    """
    info = detect()
    if info.status is not RuntimeStatus.AVAILABLE:
        raise BackendError(f"sycl is not available: {info.status.value} ({info.detail})")

    # The device is discovered from `--list-devices` rather than assumed to be
    # `SYCL0`. The old hardcoded name was also never passed on: llama.cpp
    # read no device key at all, so on a build carrying both SYCL and CUDA
    # the server picked its own preferred device and the result came back
    # labelled `sycl` having run on the other one.
    return run_via_llama_cpp(
        config,
        system,
        name="sycl",
        device_prefix="SYCL",
        backend="llama.cpp-sycl",
    )


#: Declared capability contract: truthful prerequisites.
CAPABILITIES: tuple[str, ...] = (
    "intel-gpu-required",
    "oneapi-runtime-required",
    "sycl-enabled-llama-cpp-build-required",
)
