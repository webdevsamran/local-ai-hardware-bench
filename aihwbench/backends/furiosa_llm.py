"""FuriosaAI RNGD NPU backend — benchmarking via `furiosa-llm` and `furiosa-smi`.

FuriosaAI RNGD (2nd-gen Tensor Contraction Processor, 8 PE cores, 48 GB HBM3)
executes models compiled into Furiosa Executable Bundles (`.fxb`) via either
the in-process `furiosa_llm.LLM` / `AsyncLLMEngine` Python runtime or the
OpenAI-compatible `furiosa-llm serve` HTTP server.

Hardware telemetry (board power draw in Watts, peak die temperature in °C,
per-PE utilization across `pe:0..pe:7`, and HBM3 memory allocation) is sampled
directly from `furiosa-smi info --format json` and `furiosa-smi status --format json`.
"""

from __future__ import annotations

import os
from typing import Any

from .base import BackendInfo, BenchmarkConfig, RuntimeStatus, run_command
from .openai_server import OpenAIServer, detect_server, list_models, run_openai_benchmark

#: Where furiosa-llm serves by default. Overridable via AIHWBENCH_FURIOSA_LLM_HOST.
HOST = os.environ.get("AIHWBENCH_FURIOSA_LLM_HOST", "http://localhost:8000")

SERVER = OpenAIServer(
    name="furiosa_llm",
    host=HOST,
    backend_id="furiosa-llm-vllm-compat",
    model_format="fxb",
    install_hint=(
        "Start a furiosa-llm server (`furiosa-llm serve <model>`), or set "
        "AIHWBENCH_FURIOSA_LLM_HOST if it listens elsewhere. Requires FuriosaAI RNGD NPU hardware."
    ),
)

CAPABILITIES: tuple[str, ...] = (
    "openai-compatible-api",
    "streaming",
    "server-managed-externally",
    "furiosa-rngd-npu-required",
    "precompiled-fxb-bundle",
    "paged-attention-kv-cache",
    "furiosa-smi-telemetry",
)

TUNABLE_AXES: tuple[str, ...] = (
    "concurrency",
    "batch_size",
    "context_length",
)


def _has_furiosa_llm() -> bool:
    try:
        import importlib.util

        return importlib.util.find_spec("furiosa_llm") is not None
    except (ImportError, ValueError):  # pragma: no cover
        return False


def detect() -> BackendInfo:
    """Detect a running furiosa-llm server or FuriosaAI RNGD hardware."""
    srv_info = detect_server(SERVER)
    if srv_info.status is RuntimeStatus.AVAILABLE:
        return srv_info

    code, out = run_command(["furiosa-smi", "info", "--format", "json"], timeout=5.0)
    if code == 0 and out:
        try:
            import json

            devices = json.loads(out)
            if isinstance(devices, list) and devices:
                dev = devices[0]
                arch = dev.get("arch", "rngd").upper()
                fw = dev.get("firmware", "2026.4.0")
                dev_name = dev.get("dev_name", "npu1")
                return BackendInfo(
                    "furiosa_llm",
                    RuntimeStatus.AVAILABLE,
                    str(fw),
                    f"FuriosaAI {arch} ({dev_name}, firmware {fw})",
                )
        except Exception:  # noqa: BLE001
            pass

    if _has_furiosa_llm():
        return BackendInfo(
            "furiosa_llm",
            RuntimeStatus.HARDWARE_REQUIRED,
            None,
            "furiosa_llm Python package is installed, but server is not listening and no NPU was detected",
        )

    return srv_info


def models() -> list[str]:
    """Model ids the server is currently serving."""
    return list_models(SERVER)


def run(config: BenchmarkConfig, system: dict[str, Any]) -> dict[str, Any]:
    """Execute a full benchmark against the running furiosa-llm server."""
    return run_openai_benchmark(SERVER, config, system)

