"""Qualcomm QNN — the Snapdragon NPU, reached through ONNX Runtime.

There are two ways onto a Hexagon NPU and they are not equally reachable. The
Qualcomm AI Engine Direct SDK compiles context binaries ahead of time and is
what a product ships; ONNX Runtime's QNN execution provider loads an ordinary
ONNX model and partitions it onto the NPU at session creation. The second is
what anybody benchmarking their own laptop can actually do, so it is the path
this backend measures — `pip install onnxruntime-qnn` and a quantized model.

Detection reports both, because they fail differently and the fixes differ.
The SDK being present does not make a model runnable, and the provider being
present does not mean the SDK is installed; saying "qnn not available" when one
of the two is there tells a Snapdragon owner nothing.

**The failure worth guarding is not a missing NPU, it is a quiet CPU.** The QNN
provider accepts a float32 model, loads successfully, reports itself active —
and assigns almost none of the graph to the NPU, because it wants quantized
QDQ operators. Every check that asks "did the provider load?" says yes while
an x86-class core does the work under an NPU's name. So the ONNX Runtime path
this delegates to inspects *node assignment*, not provider presence, and the
result records how much of the graph the accelerator actually took.

Untested on real hardware: no Snapdragon X machine has been available to this
project. The code path is written and unit-tested with the runtime faked.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from ._delegate import run_via_onnxruntime
from .base import BackendError, BackendInfo, BenchmarkConfig, RuntimeStatus

_COMMON_SDK_PATHS = [
    Path("C:/Qualcomm/AIStack"),
    Path(os.path.expanduser("~")) / "Qualcomm" / "AIStack",
]

QNN_PROVIDER = "QNNExecutionProvider"


def sdk_root() -> Path | None:
    """The Qualcomm AI Engine Direct SDK directory, if one is installed."""
    configured = os.environ.get("QNN_SDK_ROOT")
    candidates = [Path(configured)] if configured else []
    candidates += _COMMON_SDK_PATHS
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return None


def _has_qnn_provider() -> bool:
    try:
        import onnxruntime

        return QNN_PROVIDER in onnxruntime.get_available_providers()
    except Exception:  # noqa: BLE001 - detection must never raise
        return False


def detect() -> BackendInfo:
    """Detect a runnable QNN path, and say which half is missing."""
    provider = _has_qnn_provider()
    sdk = sdk_root()

    if provider:
        detail = f"ONNX Runtime {QNN_PROVIDER} available"
        if sdk is not None:
            detail += f"; QNN SDK at {sdk}"
        return BackendInfo("qnn", RuntimeStatus.AVAILABLE, None, detail)

    if sdk is not None:
        return BackendInfo(
            "qnn",
            RuntimeStatus.CONFIGURATION_REQUIRED,
            None,
            f"QNN SDK found at {sdk}, but ONNX Runtime has no {QNN_PROVIDER}. "
            "Install onnxruntime-qnn to benchmark through it.",
        )
    return BackendInfo(
        "qnn",
        RuntimeStatus.HARDWARE_REQUIRED,
        None,
        "Requires Qualcomm Snapdragon X (or Hexagon NPU) hardware. On such a "
        "machine, `pip install onnxruntime-qnn` provides the runnable path; "
        "the Qualcomm AI Engine Direct SDK is only needed to compile context "
        "binaries ahead of time.",
    )


def run(config: BenchmarkConfig, system: dict[str, Any]) -> dict[str, Any]:
    """Benchmark an ONNX model on the Hexagon NPU."""
    info = detect()
    if info.status is not RuntimeStatus.AVAILABLE:
        raise BackendError(f"qnn is not available: {info.status.value} ({info.detail})")
    return run_via_onnxruntime(
        config,
        system,
        name="qnn",
        device="qnn",
        backend="onnxruntime-qnn",
    )


# Declared capability contract: truthful hardware/library prerequisites.
# Detection never reports availability when these are missing.
CAPABILITIES: tuple[str, ...] = (
    "qualcomm-soc-required",
    "qnn-libs-required",
    "quantized-model-recommended",
)
