"""Vulkan backend — the vendor-neutral path, and why detection has two halves.

Vulkan is the one GPU API that runs on everything: AMD, Intel, NVIDIA, Mali,
Adreno. For a project whose point is measuring hardware people actually own,
it matters more than any vendor SDK, because it is often the only backend a
laptop's integrated GPU can use at all.

Detection asks two separate questions, and conflating them is what makes a
Vulkan report useless:

**Does the machine have Vulkan devices?** Read from `vulkaninfo`. On the
reference laptop the answer is two -- an Intel Iris Xe and an RTX 3080 Ti --
even though nothing here can currently benchmark either through Vulkan.

**Does the llama.cpp build have a Vulkan backend?** A stock CUDA build does
not, and no amount of Vulkan drivers changes that. The reference build ships
`ggml-cuda.dll` and `ggml-rpc.dll` and no `ggml-vulkan.dll`, so the honest
answer is "your hardware can, your build cannot" -- which is actionable,
unlike "not available".

That distinction is the whole value of this module. A user with a Radeon card
told "Vulkan not available" concludes their hardware is unsupported; told "two
Vulkan devices found, but this llama.cpp build has no Vulkan backend --
rebuild with -DGGML_VULKAN=ON" they know exactly what to do.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .base import BackendError, BackendInfo, BenchmarkConfig, RuntimeStatus, run_command

#: `deviceName = Intel(R) Iris(R) Xe Graphics`
_DEVICE_NAME = re.compile(r"^\s*deviceName\s*=\s*(.+?)\s*$", re.MULTILINE)


def vulkan_devices() -> list[str]:
    """GPU names Vulkan can see, or an empty list if it cannot be asked."""
    code, out = run_command(["vulkaninfo", "--summary"], timeout=30.0)
    if code != 0 or not out:
        return []
    # Deduplicated in order: vulkaninfo lists a device once per section.
    seen: dict[str, None] = {}
    for name in _DEVICE_NAME.findall(out):
        seen.setdefault(name, None)
    return list(seen)


def build_has_vulkan_backend() -> bool | None:
    """Whether the located llama.cpp ships a Vulkan backend.

    None when llama.cpp could not be found at all -- unknown, which is not the
    same as "no", and must not be reported as a missing feature of a build
    nobody located.
    """
    from .llama_cpp import _find_binary

    server = _find_binary("llama-server")
    if not server:
        return None
    directory = Path(server).parent
    if any(directory.glob("ggml-vulkan*")):
        return True
    # A statically linked build advertises Vulkan devices in its own listing.
    code, out = run_command([server, "--list-devices"], timeout=60.0)
    if code == 0 and out and "vulkan" in out.lower():
        return True
    return False


def detect() -> BackendInfo:
    """Report hardware support and build support separately."""
    devices = vulkan_devices()
    has_backend = build_has_vulkan_backend()

    if not devices:
        return BackendInfo(
            "vulkan",
            RuntimeStatus.HARDWARE_REQUIRED,
            None,
            "No Vulkan devices found. Install your GPU vendor's Vulkan driver; "
            "`vulkaninfo --summary` should list at least one device.",
        )

    listed = ", ".join(devices)
    if has_backend is None:
        return BackendInfo(
            "vulkan",
            RuntimeStatus.NOT_INSTALLED,
            None,
            f"Vulkan devices present ({listed}), but no llama.cpp was found to "
            "run them. Install llama.cpp built with -DGGML_VULKAN=ON.",
        )
    if not has_backend:
        # The case on the reference machine, and the one worth wording well.
        return BackendInfo(
            "vulkan",
            RuntimeStatus.CONFIGURATION_REQUIRED,
            None,
            f"Vulkan devices present ({listed}), but this llama.cpp build has no "
            "Vulkan backend -- it ships CUDA only. Rebuild with "
            "-DGGML_VULKAN=ON, or install a Vulkan build, to benchmark these "
            "devices. The hardware is not the limitation.",
        )
    return BackendInfo("vulkan", RuntimeStatus.AVAILABLE, None, f"Vulkan devices: {listed}")


def run(config: BenchmarkConfig, system: dict[str, Any]) -> dict[str, Any]:
    """Benchmark through llama.cpp's Vulkan backend.

    Delegates to the llama.cpp backend with the Vulkan device selected, since
    Vulkan is a build variant of the same server rather than a separate
    runtime. Refuses rather than silently falling back to CUDA: a result
    labelled `vulkan` that was produced by CUDA is worse than no result, and
    it is exactly the kind of mislabelling the comparison classifier cannot
    catch.
    """
    info = detect()
    if info.status is not RuntimeStatus.AVAILABLE:
        raise BackendError(f"vulkan is not available: {info.status.value} ({info.detail})")

    from . import llama_cpp

    extra = dict(config.extra or {})
    extra.setdefault("device", "Vulkan0")
    result = llama_cpp.run(
        BenchmarkConfig(**{**config.__dict__, "extra": extra}),
        system,
    )
    result["runtime"]["name"] = "vulkan"
    result["runtime"]["backend"] = "llama.cpp-vulkan"
    return result


#: Declared capability contract: truthful prerequisites.
CAPABILITIES: tuple[str, ...] = (
    "vulkan-driver-required",
    "vulkan-enabled-llama-cpp-build-required",
    "vendor-neutral",
)
