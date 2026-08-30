"""OpenVINO GenAI backend — detection for OpenVINO GenAI LLM pipelines.

Detection-first backend: real runs require the ``openvino_genai``
package plus an Intel-visible device. When the package is absent the
backend reports CONFIGURATION_REQUIRED; when present but no device is
visible, HARDWARE_REQUIRED. ``run()`` raises BackendError with an
actionable message until a measured pipeline path lands — results are
never fabricated.
"""

from __future__ import annotations

from typing import Any

from .base import (
    BackendError,
    BackendInfo,
    BenchmarkConfig,
    BenchmarkMetadata,
    RuntimeStatus,
)

METADATA = BenchmarkMetadata(
    name="openvino_genai",
    description="OpenVINO GenAI (LLM pipeline) on Intel CPU/GPU/NPU",
    capabilities=("llm", "openvino", "intel"),
)


def _import_openvino_genai():
    try:
        import openvino_genai  # type: ignore[import-not-found]

        return openvino_genai
    except ImportError:
        return None


def _detect_devices() -> list[str]:
    """Visible OpenVINO devices (empty when the Core is unavailable)."""
    try:
        import openvino as ov

        core = ov.Core()
        return list(core.get_available_devices())
    except Exception:  # noqa: BLE001 - detection must never raise
        return []


def detect() -> BackendInfo:
    """Detect OpenVINO GenAI plus an Intel-visible device, honestly."""
    package = _import_openvino_genai()
    version = getattr(package, "__version__", None)
    if package is None:
        return BackendInfo(
            "openvino_genai",
            RuntimeStatus.CONFIGURATION_REQUIRED,
            None,
            "Install with 'pip install openvino-genai' to enable this backend",
        )
    devices = [d for d in _detect_devices() if d.startswith(("CPU", "GPU", "NPU"))]
    if not devices:
        return BackendInfo(
            "openvino_genai",
            RuntimeStatus.HARDWARE_REQUIRED,
            version,
            "No CPU/GPU/NPU device visible to OpenVINO",
        )
    return BackendInfo(
        "openvino_genai",
        RuntimeStatus.AVAILABLE,
        version,
        f"devices: {', '.join(devices)}",
    )


def list_models() -> list[str]:
    """No local model registry for GenAI pipelines; always empty."""
    return []


def run(config: BenchmarkConfig, system: dict[str, Any]) -> dict[str, Any]:
    """Real measurements only — raise until the pipeline path exists."""
    info = detect()
    if info.status is not RuntimeStatus.AVAILABLE:
        raise BackendError(
            f"OpenVINO GenAI is not runnable here: {info.status.value} ({info.detail})"
        )
    model_dir = config.extra.get("model_dir")
    if not model_dir:
        raise BackendError(
            "OpenVINO GenAI benchmarking needs an exported model directory: "
            "pass BenchmarkConfig(extra={'model_dir': ...}) pointing at an "
            "openvino_genai.LLMPipeline model path. No synthetic results are produced."
        )
    raise BackendError(
        "Measured OpenVINO GenAI runs land with the first real pipeline "
        "integration; detection and capability metadata are available today."
    )
