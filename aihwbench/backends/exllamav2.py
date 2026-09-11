"""ExLlamaV2 backend — EXL2 quantization, which is not GGUF and does not mix.

ExLlamaV2 is the fastest path for consumer NVIDIA cards on many models, and it
earns a backend for a reason beyond speed: EXL2 supports *fractional* bits per
weight. A 4.65 bpw quantization has no GGUF equivalent, so "llama.cpp at
q4_K_M against ExLlamaV2 at 4.65 bpw" is not like-for-like — and the
comparison-safety classifier cannot tell from the quantization strings alone,
because neither string is wrong.

So this backend records the bits per weight it actually ran and declares EXL2
as its own model format rather than mapping it onto the GGUF vocabulary. A
result labelled `q4` that was really 4.65 bpw would understate its memory and
overstate the quality of every GGUF result compared against it.

Needs a CUDA GPU, PyTorch and the `exllamav2` package. None is installed here,
so this detects and says which is missing rather than pretending.
"""

from __future__ import annotations

import importlib.util
from typing import Any

from .base import BackendError, BackendInfo, BenchmarkConfig, RuntimeStatus


def _installed(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):  # pragma: no cover - malformed install
        return False


def detect() -> BackendInfo:
    """Report which prerequisite is missing, not merely that one is."""
    has_torch = _installed("torch")
    has_exllama = _installed("exllamav2")

    if has_exllama and has_torch:
        try:
            import torch

            if not torch.cuda.is_available():
                return BackendInfo(
                    "exllamav2",
                    RuntimeStatus.HARDWARE_REQUIRED,
                    None,
                    "exllamav2 and torch are installed but torch reports no CUDA "
                    "device. ExLlamaV2 has no CPU path.",
                )
            version = getattr(importlib.import_module("exllamav2"), "__version__", None)
            return BackendInfo("exllamav2", RuntimeStatus.AVAILABLE, version)
        except Exception as exc:  # pragma: no cover - import failures vary
            return BackendInfo("exllamav2", RuntimeStatus.CONFIGURATION_REQUIRED, None, str(exc))

    missing = [
        name for name, present in (("torch", has_torch), ("exllamav2", has_exllama)) if not present
    ]
    return BackendInfo(
        "exllamav2",
        RuntimeStatus.NOT_INSTALLED,
        None,
        f"Missing: {', '.join(missing)}. Install a CUDA build of PyTorch and "
        "`pip install exllamav2`. It needs an NVIDIA GPU and EXL2-format "
        "weights, which are not interchangeable with GGUF.",
    )


def run(config: BenchmarkConfig, system: dict[str, Any]) -> dict[str, Any]:
    """Benchmark an EXL2 model.

    Refuses when the prerequisites are absent rather than falling back: there
    is no CPU path, and a result labelled `exllamav2` produced by something
    else would be unattributable.
    """
    info = detect()
    if info.status is not RuntimeStatus.AVAILABLE:
        raise BackendError(f"exllamav2 is not available: {info.status.value} ({info.detail})")
    raise BackendError(
        "ExLlamaV2 execution is not implemented. Detection is wired so a machine "
        "that has it reports so honestly; running it needs EXL2 weights and a "
        "maintainer with the hardware to validate against."
    )


#: Declared capability contract: truthful prerequisites.
CAPABILITIES: tuple[str, ...] = (
    "nvidia-gpu-required",
    "pytorch-cuda-required",
    "exl2-weights-required",
    "fractional-bits-per-weight",
    "not-comparable-with-gguf-quantization-labels",
)
