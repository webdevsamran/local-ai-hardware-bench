"""Backend registry.

Each runtime module exposes detect() and run(). The registry maps CLI
runtime names to modules. Third-party backends may register via the
Python entry point group ``aihwbench.backends`` (see
docs/guides/plugin-api.md) — each entry maps a runtime name to a module
exposing ``detect()`` and ``run()``.
"""

from __future__ import annotations

from typing import Any

from . import (
    hailo,
    lemonade,
    llama_cpp,
    lmstudio,
    mlx,
    ollama,
    onnxruntime,
    openvino,
    openvino_genai,
    qnn,
    rocm,
    tensorrt,
    windows_ml,
)
from .base import (
    BackendError,
    BackendInfo,
    BenchmarkConfig,
    BenchmarkMetadata,
    RuntimeStatus,
)

BACKEND_API_VERSION = 1

BACKENDS: dict[str, Any] = {
    "ollama": ollama,
    "llama.cpp": llama_cpp,
    "onnxruntime": onnxruntime,
    "openvino": openvino,
    "openvino_genai": openvino_genai,
    "lemonade": lemonade,
    "lmstudio": lmstudio,
    "rocm": rocm,
    "mlx": mlx,
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
    "lms": "lmstudio",
}

ENTRY_POINT_GROUP = "aihwbench.backends"
_plugin_loaded = False


def _load_entry_points() -> None:
    """Merge third-party backends from aihwbench.backends entry points."""
    global _plugin_loaded
    if _plugin_loaded:
        return
    _plugin_loaded = True
    try:
        from importlib.metadata import entry_points
    except ImportError:
        return
    try:
        eps = entry_points(group=ENTRY_POINT_GROUP)
    except TypeError:
        return
    for ep in eps:
        try:
            module = ep.load()
        except Exception as exc:  # noqa: BLE001 - plugin errors must not break detection
            BACKENDS[ep.name] = {"_load_error": f"entry point {ep.name!r} failed: {exc}"}
            continue
        if module is not None and ep.name not in BACKENDS:
            BACKENDS[ep.name] = module


def resolve(name: str) -> Any:
    """Resolve a runtime name (with aliases) to its backend module."""
    _load_entry_points()
    key = ALIASES.get(name.lower(), name.lower())
    if key not in BACKENDS:
        raise BackendError(f"unknown runtime {name!r}. Available: {', '.join(sorted(BACKENDS))}")
    module = BACKENDS[key]
    if isinstance(module, dict) and "_load_error" in module:
        raise BackendError(module["_load_error"])
    return module


def detect_all() -> list[dict[str, Any]]:
    """Detect every registered runtime. Never raises."""
    _load_entry_points()
    results = []
    for name in sorted(BACKENDS):
        module = BACKENDS[name]
        if isinstance(module, dict) and "_load_error" in module:
            results.append(
                {
                    "name": name,
                    "status": RuntimeStatus.NOT_AVAILABLE.value,
                    "version": None,
                    "detail": module["_load_error"],
                }
            )
            continue
        try:
            results.append(module.detect().as_dict())
        except Exception as exc:  # noqa: BLE001 - detection must not crash
            results.append(
                {
                    "name": name,
                    "status": RuntimeStatus.NOT_AVAILABLE.value,
                    "version": None,
                    "detail": f"detection error: {exc}",
                }
            )
    return results


def backend_metadata(name: str) -> BenchmarkMetadata | None:
    """Return a backend's declared metadata, synthesizing from its
    CAPABILITIES tuple when it provides no full metadata block
    (#7/#8/#10/#11 capability contract)."""
    module = resolve(name)
    md = getattr(module, "METADATA", None)
    caps = getattr(module, "CAPABILITIES", ())
    if md is None and caps:
        return BenchmarkMetadata(name=name, description=name, capabilities=tuple(caps))
    return md


__all__ = [
    "BACKENDS",
    "ALIASES",
    "BACKEND_API_VERSION",
    "ENTRY_POINT_GROUP",
    "BackendError",
    "BackendInfo",
    "BenchmarkConfig",
    "BenchmarkMetadata",
    "RuntimeStatus",
    "backend_metadata",
    "detect_all",
    "resolve",
]
