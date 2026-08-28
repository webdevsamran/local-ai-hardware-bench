"""Backend base classes and shared types.

Every runtime backend implements:

  detect()  -> BackendInfo   (is the runtime installed/usable here?)
  run()     -> dict          (a schema-1.0 result document)

Backends must never fabricate results. If a benchmark cannot run, they
raise BackendError with an actionable message.
"""

from __future__ import annotations

import enum
import hashlib
import subprocess
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
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


def file_sha256(path: str | Path, chunk_size: int = 1 << 20) -> str:
    """Streaming SHA-256 of a file (hex digest), for model identity."""
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_input_specs(
    specs: Iterable[tuple[str, str, Sequence[object]]],
) -> dict[str, dict[str, Any]]:
    """Resolve graph-model input metadata into concrete, zero-fillable specs.

    Accepts ``(name, type_string, declared_shape)`` triples from any graph
    runtime (ONNX Runtime metadata, OpenVINO input nodes, ...). Returns a
    mapping of input name to ``{"shape": [ints], "dtype": "<numpy name>"}``.

    - Dynamic/unknown/static-zero dimensions are pinned to 1 (documented
      in the result's reproducibility block as ``graph_inputs``).
    - Element-type strings are normalized across runtime vocabularies
      (``tensor(int64)`` and ``i64`` both map to ``int64``).
    - Unsupported dtypes (e.g. bfloat16, strings) fail closed with
      ``BackendError`` instead of silently mis-typing the input.

    Every declared input is resolved — callers must feed ALL inputs to the
    runtime, not only the first.
    """
    resolved: dict[str, dict[str, Any]] = {}
    for name, type_str, declared_shape in specs:
        shape = [int(d) if isinstance(d, int) and not isinstance(d, bool) and d > 0 else 1 for d in declared_shape]
        resolved[name] = {"shape": shape, "dtype": _normalize_dtype(name, type_str)}
    if not resolved:
        raise BackendError("model declares no inputs; cannot construct a benchmark feed")
    return resolved


def _normalize_dtype(input_name: str, type_str: str) -> str:
    """Map a runtime element-type string to a numpy dtype name. Fails closed."""
    t = type_str.lower()
    # Order matters: wider/unsigned names must match before their substrings.
    if "double" in t or "float64" in t:
        return "float64"
    if "bfloat16" in t or "bf16" in t:
        raise BackendError(
            f"input {input_name!r} has dtype {type_str!r}; bfloat16 cannot be "
            "zero-filled as a numpy array — provide an input-preparation hook"
        )
    if "float16" in t or "half" in t or "f16" in t:
        return "float16"
    if "float" in t or "f32" in t:
        return "float32"
    if "uint64" in t or "ui64" in t:
        return "uint64"
    if "uint32" in t or "ui32" in t:
        return "uint32"
    if "uint16" in t or "ui16" in t:
        return "uint16"
    if "uint8" in t or "ui8" in t:
        return "uint8"
    if "int64" in t or "i64" in t or "long" in t:
        return "int64"
    if "int32" in t or "i32" in t:
        return "int32"
    if "int16" in t or "i16" in t:
        return "int16"
    if "int8" in t or "i8" in t:
        return "int8"
    if "bool" in t:
        return "bool"
    raise BackendError(
        f"input {input_name!r} has unsupported dtype {type_str!r}; cannot "
        "construct a deterministic zero input (supported: float16/32/64, "
        "int8/16/32/64, uint8/16/32/64, bool)"
    )
