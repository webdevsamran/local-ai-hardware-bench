"""Backend base classes and shared types.

Every runtime backend implements:

  detect()  -> BackendInfo   (is the runtime installed/usable here?)
  run()     -> dict          (a schema-1.0 result document)

Backends must never fabricate results. If a benchmark cannot run, they
raise BackendError with an actionable message.
"""

from __future__ import annotations

import enum
import subprocess
from dataclasses import dataclass, field
from typing import Any


class RuntimeStatus(str, enum.Enum):
    """Lifecycle states reported by backend detection."""

    AVAILABLE = "AVAILABLE"
    NOT_INSTALLED = "NOT_INSTALLED"
    NOT_AVAILABLE = "NOT_AVAILABLE"
    UNSUPPORTED_PLATFORM = "UNSUPPORTED_PLATFORM"
    HARDWARE_REQUIRED = "HARDWARE_REQUIRED"
    CONFIGURATION_REQUIRED = "CONFIGURATION_REQUIRED"


class BackendError(RuntimeError):
    """Raised when a benchmark cannot be executed."""


@dataclass
class BackendInfo:
    """Detection result for one runtime."""

    name: str
    status: RuntimeStatus
    version: str | None = None
    detail: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "version": self.version,
            "detail": self.detail,
        }


@dataclass
class BenchmarkMetadata:
    """Declarative backend metadata for the plugin registry."""

    name: str
    description: str
    api_version: int = 1
    capabilities: tuple[str, ...] = ()


@dataclass
class BenchmarkConfig:
    """Parameters for one benchmark run. All values are recorded in the
    result document's reproducibility block."""

    model: str
    prompt: str = "Explain what a token is in large language models, in two sentences."
    max_tokens: int = 128
    warmup_runs: int = 2
    iterations: int = 5
    temperature: float = 0.0
    seed: int = 42
    context_length: int = 2048
    device: str = "auto"
    extra: dict[str, Any] = field(default_factory=dict)


def new_run_id(prefix: str) -> str:
    """Collision-resistant run id: <prefix>-<epoch>-<uuid8>."""
    import time
    import uuid

    return f"{prefix}-{int(time.time())}-{uuid.uuid4().hex[:8]}"

def run_command(cmd: list[str], timeout: float = 15.0) -> tuple[int, str]:
    """Run a command, returning (returncode, combined output)."""
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        return proc.returncode, (proc.stdout + proc.stderr).strip()
    except FileNotFoundError:
        return 127, f"executable not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, "command timed out"


def which(executable: str) -> str | None:
    """Locate an executable on PATH without executing it."""
    from shutil import which as _which

    return _which(executable)
