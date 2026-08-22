"""Backend registry.

Each runtime module exposes detect() and run(). The registry maps CLI
runtime names to those modules so new backends can be added by adding
one entry here.
"""

from __future__ import annotations

from typing import Any

from . import (
    hailo,
    llama_cpp,
    ollama,
    onnxruntime,
    openvino,
    qnn,
    rocm,
    tensorrt,
    windows_ml,
)
from .base import BackendError, BackendInfo, BenchmarkConfig, RuntimeStatus

BACKENDS: dict[str, Any] = {
    "ollama": ollama,
    "llama.cpp": llama_cpp,
    "onnxruntime": onnxruntime,
    "openvino": openvino,
    "rocm": rocm,
    "windows_ml": windows_ml,
    "qnn": qnn,
    "tensorrt": tensorrt,
    "hailo": hailo,
}

ALIASES: dict[str, str] = {
    "llamacpp": "llama.cpp",
    "llama-cpp": "llama.cpp",
    "ort": "onnxruntime",
    "trt": "tensorrt",
    "hailort": "hailo",
}


def resolve(name: str) -> Any:
    """Resolve a runtime name (with aliases) to its backend module."""
    key = ALIASES.get(name.lower(), name.lower())
    if key not in BACKENDS:
        raise BackendError(
            f"unknown runtime {name!r}. Available: {', '.join(sorted(BACKENDS))}"
        )
    return BACKENDS[key]


def detect_all() -> list[dict[str, Any]]:
    """Detect every registered runtime. Never raises."""
    results = []
    for name in sorted(BACKENDS):
        try:
            info: BackendInfo = BACKENDS[name].detect()
            results.append(info.as_dict())
        except Exception as exc:  # noqa: BLE001 - detection must not crash
            results.append({
                "name": name,
                "status": RuntimeStatus.NOT_AVAILABLE.value,
                "version": None,
                "detail": f"detection error: {exc}",
            })
    return results


__all__ = [
    "BACKENDS",
    "ALIASES",
    "BackendError",
    "BackendInfo",
    "BenchmarkConfig",
    "RuntimeStatus",
    "detect_all",
    "resolve",
]
