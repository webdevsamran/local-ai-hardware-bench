"""Microsoft Windows ML — DirectML, measured through ONNX Runtime.

Windows ML is not a separate engine. It is an OS-integrated ONNX Runtime with
the DirectML execution provider underneath, so this backend measures the thing
itself rather than a lookalike: the same provider, on the same DirectX 12
device, through the loop every other ONNX result here comes from.

DirectML is the broadest GPU path on Windows — any DirectX 12 device, which
means AMD and Intel and Qualcomm as well as NVIDIA. On a machine with no
vendor SDK installed at all it is frequently the only accelerator a model can
reach, which makes it worth measuring properly rather than listing.

Verified on the reference machine: 101 of 104 nodes of MobileNetV2 ran on the
DirectML provider and 3 on the CPU, at 82.9 inferences per second. The node
split is recorded in every result, because "the provider loaded" and "the GPU
ran the model" are different claims and only the second one is interesting.
"""

from __future__ import annotations

import platform
from typing import Any

from ._delegate import run_via_onnxruntime
from .base import BackendError, BackendInfo, BenchmarkConfig, RuntimeStatus


def _has_directml() -> bool:
    """Whether ONNX Runtime here can reach a DirectX 12 device."""
    try:
        import onnxruntime

        return "DmlExecutionProvider" in onnxruntime.get_available_providers()
    except Exception:  # noqa: BLE001 - detection must never raise
        return False


def detect() -> BackendInfo:
    """Detect Windows ML availability by OS version."""
    if platform.system() != "Windows":
        return BackendInfo(
            "windows_ml",
            RuntimeStatus.UNSUPPORTED_PLATFORM,
            None,
            "Windows ML is only available on Windows",
        )
    build = int(platform.version().split(".")[2]) if platform.version().count(".") >= 2 else 0
    if build >= 17763:  # 1809 introduced Windows ML
        # The OS component being present is not the question -- it always is,
        # on a supported build. What decides whether anything can be measured
        # is whether ONNX Runtime here has the DirectML provider, so that is
        # what availability reports. Saying CONFIGURATION_REQUIRED on a machine
        # that can run today sends someone looking for a missing OS feature.
        if _has_directml():
            return BackendInfo(
                "windows_ml",
                RuntimeStatus.AVAILABLE,
                f"build {build}",
                "DirectML execution provider available via ONNX Runtime",
            )
        return BackendInfo(
            "windows_ml",
            RuntimeStatus.CONFIGURATION_REQUIRED,
            f"build {build}",
            "OS component present, but ONNX Runtime has no DmlExecutionProvider: "
            "pip install onnxruntime-directml",
        )
    return BackendInfo(
        "windows_ml",
        RuntimeStatus.NOT_AVAILABLE,
        f"build {build}",
        "Windows 10 1809+ required",
    )


def run(config: BenchmarkConfig, system: dict[str, Any]) -> dict[str, Any]:
    """Benchmark an ONNX model on a DirectX 12 device."""
    info = detect()
    if info.status not in (RuntimeStatus.CONFIGURATION_REQUIRED, RuntimeStatus.AVAILABLE):
        raise BackendError(f"windows_ml is not available: {info.status.value} ({info.detail})")
    return run_via_onnxruntime(
        config,
        system,
        name="windows_ml",
        device="dml",
        backend="onnxruntime-directml",
    )
