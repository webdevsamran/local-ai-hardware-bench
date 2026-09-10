"""SGLang backend — benchmarking via its OpenAI-compatible server.

SGLang is the other serving engine in Bench360's comparison set, and its
RadixAttention prefix cache makes it behave differently from vLLM on exactly
the workloads this project measures: repeated prompts and multi-turn
conversations, where a cache hit turns prefill into almost nothing.

That is worth stating plainly, because it is a way to be accidentally wrong
here. A benchmark that sends the same prompt every iteration measures the
cache after the first run, not the model. This project's warm-up runs happen
before measurement precisely so the steady state is what gets recorded -- but
a prefix-cached steady state and an uncached one are different measurements,
and comparing an SGLang number against a vLLM number without knowing which
was cached is the error the comparison classifier exists to catch.

As with vLLM, the server is never launched here: its startup flags decide
what is being measured.
"""

from __future__ import annotations

import os
from typing import Any

from .base import BackendInfo, BenchmarkConfig
from .openai_server import OpenAIServer, detect_server, list_models, run_openai_benchmark

#: SGLang's default port. Overridable for machines serving several engines.
HOST = os.environ.get("AIHWBENCH_SGLANG_HOST", "http://localhost:30000")

SERVER = OpenAIServer(
    name="sglang",
    host=HOST,
    backend_id="sglang-openai-api",
    model_format="safetensors",
    install_hint=(
        "Start an SGLang server (`python -m sglang.launch_server --model-path "
        "<model>`), or set AIHWBENCH_SGLANG_HOST if it listens elsewhere. "
        "Install: pip install 'sglang[all]' (Linux; NVIDIA or ROCm GPU required)"
    ),
)

CAPABILITIES: tuple[str, ...] = (
    "openai-compatible-api",
    "streaming",
    "server-managed-externally",
    "prefix-cache",
)


def detect() -> BackendInfo:
    """Detect a running SGLang server."""
    return detect_server(SERVER)


def models() -> list[str]:
    """Model ids the server is currently serving."""
    return list_models(SERVER)


def run(config: BenchmarkConfig, system: dict[str, Any]) -> dict[str, Any]:
    """Execute a full benchmark against the running SGLang server."""
    return run_openai_benchmark(SERVER, config, system)
