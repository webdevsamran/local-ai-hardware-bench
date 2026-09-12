"""AMD Lemonade Server — Ryzen AI, over the protocol the project already speaks.

Lemonade (https://github.com/amd/lemonade) puts an OpenAI-compatible HTTP
server in front of AMD's Ryzen AI stack, which means the NPU is reachable by
exactly the path vLLM, SGLang and LM Studio are reached by. Its endpoints live
under `/api/v1/` rather than `/v1/`, and that prefix is the only thing that
made it look like a different problem.

This was detection-only on the grounds that "no validated measurement protocol
exists for this runtime". That was true of the *runtime* and not of the
*protocol*: streaming chat completions with a usage block is the same contract
three other backends here already measure, and reusing it means Lemonade gets
the same TTFT definition, the same inter-token series and the same refusal to
count SSE chunks as tokens — rather than a fourth interpretation that drifts.

**What a result here does and does not say.** Lemonade decides internally
whether a model runs on the Ryzen AI NPU, the integrated GPU or the CPU, and
the OpenAI protocol carries no field for which one it chose. So a result
records the runtime honestly and does not claim the NPU ran it. Anyone
publishing one should say which device Lemonade reported loading; the project
would rather have an unattributed measurement than an invented attribution.

Untested on real hardware: no Ryzen AI machine has been available here.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from .base import (
    BackendError,
    BackendInfo,
    BenchmarkConfig,
    BenchmarkMetadata,
    RuntimeStatus,
    run_command,
    server_is_listening,
)
from .openai_server import OpenAIServer, run_openai_benchmark

LEMONADE_PORT = 8000

METADATA = BenchmarkMetadata(
    name="lemonade",
    description="AMD Lemonade Server (Ryzen AI) over its OpenAI-compatible API",
    api_version=1,
    # Was deliberately empty while this backend could not measure anything, so
    # that no registry or tooling introspection could present it as capable.
    # It can measure now, and leaving the tuple empty would understate it in
    # the same way the old description overstated the obstacle.
    capabilities=("llm", "openai-api", "amd", "ryzen-ai"),
)


def _health(port: int = LEMONADE_PORT, timeout: float = 2.0) -> dict[str, Any] | None:
    """One health probe against the local Lemonade server; None if down.

    The TCP pre-flight is what makes "down" cheap: a connect to a closed local
    port takes 2 seconds to refuse on the reference machine, and the server
    being absent is the ordinary case on a machine without Ryzen AI.
    """
    if not server_is_listening(f"http://127.0.0.1:{port}"):
        return None
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/api/v1/health", timeout=timeout
        ) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data if isinstance(data, dict) else {}
    except (urllib.error.URLError, OSError, json.JSONDecodeError, ValueError):
        return None


def detect() -> BackendInfo:
    """Detect the Lemonade Server CLI and/or a responding local server."""
    version: str | None = None
    for cli in ("lemonade-server-dev", "lemonade-server"):
        code, out = run_command([cli, "--version"], timeout=10.0)
        if code == 0 and out.strip():
            version = out.strip().splitlines()[0].strip()
            break
    health = _health()
    if health is not None:
        return BackendInfo("lemonade", RuntimeStatus.AVAILABLE, version)
    if version:
        return BackendInfo(
            "lemonade",
            RuntimeStatus.CONFIGURATION_REQUIRED,
            version,
            "CLI installed but server not responding on port 8000; "
            "start it with 'lemonade-server serve'",
        )
    return BackendInfo(
        "lemonade",
        RuntimeStatus.NOT_INSTALLED,
        None,
        "Install Lemonade Server (https://github.com/amd/lemonade); "
        "Ryzen AI / NPU hardware required for acceleration",
    )


#: Lemonade's OpenAI-compatible surface. The host carries the `/api` prefix so
#: the shared client's `/v1/...` paths land on `/api/v1/...`, which is where
#: Lemonade serves them.
SERVER = OpenAIServer(
    name="lemonade",
    host=f"http://127.0.0.1:{LEMONADE_PORT}/api",
    backend_id="lemonade-openai-api",
    model_format="onnx-genai",
    install_hint=(
        "Start Lemonade Server (`lemonade-server serve`) on a Ryzen AI machine. "
        "Install: https://github.com/amd/lemonade"
    ),
)


def run(config: BenchmarkConfig, system: dict[str, Any]) -> dict[str, Any]:
    """Benchmark a model served by Lemonade.

    Detection goes through Lemonade's own `/api/v1/health` rather than the
    generic model listing, because that endpoint is what distinguishes
    Lemonade from any other process holding port 8000 -- vLLM's default port
    is the same one.
    """
    info = detect()
    if info.status is not RuntimeStatus.AVAILABLE:
        raise BackendError(f"Lemonade is not available: {info.status.value} ({info.detail})")
    return run_openai_benchmark(SERVER, config, system)
