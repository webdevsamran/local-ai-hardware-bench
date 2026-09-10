"""vLLM backend — benchmarking via its OpenAI-compatible server.

vLLM is the serving engine most local-inference comparisons are measured
against, and the one Bench360 puts at the centre of its study. Bench360 runs
it only on datacenter GPUs; the point of supporting it here is the opposite
case -- the same engine on hardware someone actually owns, published next to
llama.cpp and Ollama results for the same model, with the classifier saying
when those numbers may be compared.

Detection is a GET of /v1/models against a server the user already started.
This backend never launches one: vLLM's startup flags (tensor parallelism,
GPU memory fraction, quantization, KV-cache dtype) change what is being
measured, and a benchmark that chose them silently would be reporting on a
configuration the operator never saw.
"""

from __future__ import annotations

import os
from typing import Any

from .base import BackendInfo, BenchmarkConfig
from .openai_server import OpenAIServer, detect_server, list_models, run_openai_benchmark

#: Where vLLM serves by default. Overridable because a machine running more
#: than one engine cannot give both port 8000.
HOST = os.environ.get("AIHWBENCH_VLLM_HOST", "http://localhost:8000")

SERVER = OpenAIServer(
    name="vllm",
    host=HOST,
    backend_id="vllm-openai-api",
    model_format="safetensors",
    install_hint=(
        "Start a vLLM server (`vllm serve <model>`), or set "
        "AIHWBENCH_VLLM_HOST if it listens elsewhere. Install: pip install vllm "
        "(Linux; NVIDIA or ROCm GPU required)"
    ),
)

# Declared capability contract: what this backend can and cannot apply.
CAPABILITIES: tuple[str, ...] = (
    "openai-compatible-api",
    "streaming",
    "server-managed-externally",
)


def detect() -> BackendInfo:
    """Detect a running vLLM server."""
    return detect_server(SERVER)


def models() -> list[str]:
    """Model ids the server is currently serving."""
    return list_models(SERVER)


def run(config: BenchmarkConfig, system: dict[str, Any]) -> dict[str, Any]:
    """Execute a full benchmark against the running vLLM server."""
    return run_openai_benchmark(SERVER, config, system)
