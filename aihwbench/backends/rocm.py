"""AMD ROCm — measured through whichever engine owns the model artifact.

ROCm is not an inference engine, it is AMD's compute stack, and two of the
engines this project already drives sit on top of it: llama.cpp's HIP build
runs GGUF models on a Radeon card, and ONNX Runtime's ROCm provider runs ONNX
graphs on one. So this backend dispatches on the artifact rather than owning a
benchmark loop of its own — a third copy of "start the server, time the
tokens" is a third thing to drift, and on a machine nobody here has, drift is
invisible.

**Detection has two halves, and reporting one as the other is what makes an
AMD report useless.** "Is there a Radeon card with a ROCm driver?" and "does
the llama.cpp build on this machine have a HIP backend?" are different
questions with different fixes. A user told "rocm not available" concludes
their hardware is unsupported; told "ROCm 6.2 present, but this llama.cpp build
has no HIP backend — rebuild with -DGGML_HIP=ON" they know what to do.

**Windows is a real limitation, not a missing feature.** AMD ships the HIP SDK
for Windows, but the full ROCm runtime — and every llama.cpp HIP build worth
measuring — is Linux. Detection says so rather than reporting a Windows machine
with a Radeon card as capable and failing later.

Untested on real hardware: no AMD GPU has been available to this project. The
code path is written and unit-tested with the vendor calls faked; the honest
status is "should work, never observed", and `docs/hardware-needed.md` says so.
"""

from __future__ import annotations

import platform
from pathlib import Path
from typing import Any

from ._delegate import run_via_llama_cpp, run_via_onnxruntime
from .base import BackendError, BackendInfo, BenchmarkConfig, RuntimeStatus, run_command

#: llama.cpp names its HIP devices `ROCm0`, `ROCm1`, ... in `--list-devices`.
LLAMA_DEVICE_PREFIX = "ROCm"


def rocm_version() -> str | None:
    """The installed ROCm version, or None when the stack is absent."""
    for tool, flag in (("hipconfig", "--version"), ("rocminfo", None)):
        code, out = run_command([tool] + ([flag] if flag else []), timeout=10.0)
        if code == 0 and out.strip():
            return out.strip().splitlines()[0].strip()
    return None


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
    version = rocm_version()
    if version is None:
        return BackendInfo(
            "rocm",
            RuntimeStatus.HARDWARE_REQUIRED,
            None,
            "Install ROCm from https://rocm.docs.amd.com (requires supported AMD GPU)",
        )
    return BackendInfo("rocm", RuntimeStatus.AVAILABLE, version, version)


def run(config: BenchmarkConfig, system: dict[str, Any]) -> dict[str, Any]:
    """Benchmark on a Radeon card, through the engine that reads the model.

    An `.onnx` file goes to ONNX Runtime's ROCm provider; anything else is a
    GGUF for llama.cpp's HIP build. The dispatch is on the artifact because
    that is what actually decides which engine can open it, rather than on a
    flag someone has to remember.
    """
    info = detect()
    if info.status is not RuntimeStatus.AVAILABLE:
        raise BackendError(f"rocm is not available: {info.status.value} ({info.detail})")

    model_path = (config.extra or {}).get("model_path")
    if model_path and Path(str(model_path)).suffix.lower() == ".onnx":
        return run_via_onnxruntime(
            config,
            system,
            name="rocm",
            device="rocm",
            backend="onnxruntime-rocm",
        )
    return run_via_llama_cpp(
        config,
        system,
        name="rocm",
        device_prefix=LLAMA_DEVICE_PREFIX,
        backend="llama.cpp-hip",
    )


# Declared capability contract: truthful hardware/library prerequisites.
# Detection never reports availability when these are missing.
CAPABILITIES: tuple[str, ...] = (
    "amd-gpu-required",
    "hip-runtime-required",
    "linux-primary",
)
