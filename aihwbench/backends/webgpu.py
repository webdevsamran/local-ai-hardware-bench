"""WebGPU/wasm backend — inference in a browser, which is a different question.

A browser runtime is not a faster way to run a model. It is the only way to run
one on a machine where nothing can be installed: a locked-down work laptop, a
Chromebook, a phone. For a project about hardware people actually have, that
population is large and completely unmeasured.

It is also the hardest thing here to measure honestly, and the reasons are
worth stating rather than discovering:

**The browser is part of the hardware under test.** Chrome and Firefox map
WebGPU onto different native APIs on the same machine, so a result is a
property of the browser as much as of the GPU. The browser and its version
belong in the result or the number is unattributable.

**The sandbox hides the things this project measures.** No power telemetry, no
temperature, no VRAM figure, no process memory. Every energy and thermal field
is unavailable by construction -- not "not measured yet", but unmeasurable
from inside a page -- and they must be reported as such rather than as zeros.

**Timing is deliberately coarsened.** Browsers reduce timer resolution and jitter
it to defeat side-channel attacks, so inter-token latency below a few
milliseconds cannot be resolved.

So detection reports what a browser-based measurement can and cannot answer,
and `run` refuses rather than producing a result with the honest fields
silently null.
"""

from __future__ import annotations

import shutil
from typing import Any

from .base import BackendError, BackendInfo, BenchmarkConfig, RuntimeStatus, run_command

#: Fields a page cannot measure, whatever the runtime does. Reported so a
#: consumer knows the nulls are structural rather than missing data.
UNMEASURABLE_IN_BROWSER: tuple[str, ...] = (
    "average_power_watts",
    "peak_vram_mb",
    "max_temperature_c",
    "avg_gpu_util_percent",
)


def browsers_present() -> list[str]:
    """Browsers on PATH that support WebGPU in a current release."""
    candidates = {
        "chrome": ("chrome", "google-chrome", "chromium"),
        "edge": ("msedge",),
        "firefox": ("firefox",),
    }
    found = []
    for label, names in candidates.items():
        if any(shutil.which(name) for name in names):
            found.append(label)
    return found


def node_has_webgpu() -> bool:
    """Whether the installed Node can run a headless WebGPU harness.

    Node exposes WebGPU from 22 onward behind a flag. Checked rather than
    assumed, because "a browser is installed" says nothing about whether an
    unattended benchmark can drive one.
    """
    code, out = run_command(["node", "--version"], timeout=20.0)
    if code != 0 or not out:
        return False
    try:
        major = int(out.strip().lstrip("v").split(".")[0])
    except (ValueError, IndexError):
        return False
    return major >= 22


def detect() -> BackendInfo:
    browsers = browsers_present()
    harness = node_has_webgpu()

    if not browsers and not harness:
        return BackendInfo(
            "webgpu",
            RuntimeStatus.NOT_INSTALLED,
            None,
            "No WebGPU-capable browser or Node 22+ found. WebGPU benchmarking "
            "needs one of them to host the runtime.",
        )

    where = ", ".join(browsers) if browsers else "Node"
    return BackendInfo(
        "webgpu",
        RuntimeStatus.CONFIGURATION_REQUIRED,
        None,
        f"{where} present, but no WebGPU benchmark harness is wired up. A "
        "browser result also cannot carry power, VRAM or temperature -- the "
        "sandbox does not expose them -- so it answers 'does it run, and how "
        "fast', not the energy questions this project asks elsewhere.",
    )


def run(config: BenchmarkConfig, system: dict[str, Any]) -> dict[str, Any]:
    """Refuse until a harness exists, rather than emit a half-filled result.

    A WebGPU result with null power, null VRAM and null temperature is
    indistinguishable from a native result whose telemetry failed, and the
    comparison classifier reads two nulls as agreement. Producing one would
    quietly make browser numbers comparable with native ones.
    """
    info = detect()
    raise BackendError(
        f"webgpu is not available: {info.status.value} ({info.detail}). "
        f"Fields a browser cannot measure: {', '.join(UNMEASURABLE_IN_BROWSER)}."
    )


#: Declared capability contract: truthful prerequisites and limits.
CAPABILITIES: tuple[str, ...] = (
    "browser-or-node22-required",
    "no-power-telemetry",
    "no-vram-telemetry",
    "coarsened-timer-resolution",
    "browser-is-part-of-the-system-under-test",
)
