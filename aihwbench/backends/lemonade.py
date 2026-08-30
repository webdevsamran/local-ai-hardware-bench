"""AMD Lemonade Server backend — detection-only (issue #9).

Lemonade (https://github.com/amd/lemonade) exposes an OpenAI-compatible
HTTP server (default port 8000) targeting AMD Ryzen AI / NPU hardware.

Status: detection only. The benchmark path is NOT implemented because no
validated measurement protocol exists yet for this runtime; ``run()``
raises a clean ``BackendError`` instead of producing misleading numbers.
``METADATA.capabilities`` is empty so this adapter can never look
benchmark-capable in registry or tooling introspection.
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
)

LEMONADE_PORT = 8000

METADATA = BenchmarkMetadata(
    name="lemonade",
    description=(
        "AMD Lemonade Server (Ryzen AI) — detection only; "
        "benchmark path pending a validated protocol (issue #9)"
    ),
    api_version=1,
    capabilities=(),
)


def _health(port: int = LEMONADE_PORT, timeout: float = 2.0) -> dict[str, Any] | None:
    """One health probe against the local Lemonade server; None if down."""
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


def run(config: BenchmarkConfig, system: dict[str, Any]) -> dict[str, Any]:
    """Refuse to benchmark: detection-only until a protocol is validated."""
    info = detect()
    if info.status is not RuntimeStatus.AVAILABLE:
        raise BackendError(f"Lemonade is not available: {info.status.value} ({info.detail})")
    raise BackendError(
        "Lemonade benchmarking is not implemented yet: no validated "
        "measurement protocol exists for this runtime (issue #9). "
        "Detection-only backends never produce estimated numbers."
    )
