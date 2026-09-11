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
import socket
import subprocess
import urllib.parse
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


#: Execution-provider and OpenVINO device names, mapped to the device
#: vocabulary `runtime.device` uses.
_RESOLVED_DEVICE_NAMES = {
    "cpuexecutionprovider": "cpu",
    "cudaexecutionprovider": "cuda",
    "dmlexecutionprovider": "dml",
    "tensorrtexecutionprovider": "cuda",
    "openvinoexecutionprovider": "cpu",
    "cpu": "cpu",
    "gpu": "gpu",
    "npu": "npu",
    "auto": "auto",
}


#: How long to wait for a local TCP connect before deciding nothing is there.
#:
#: Generous for the thing being measured: a server listening on loopback
#: accepts in well under a millisecond, so this is a margin of hundreds of
#: times over. It is short because the *absent* case is the common one --
#: most people run one of these servers, not five.
LOCAL_PROBE_TIMEOUT = 0.4


def server_is_listening(url: str, timeout: float = LOCAL_PROBE_TIMEOUT) -> bool:
    """Whether anything accepts a TCP connection at `url`'s host and port.

    A pre-flight for the HTTP-server backends, which is worth its existence
    because of how slowly this machine says "no". A connect to a closed port on
    127.0.0.1 takes **2.0 seconds** here before refusing, and `localhost`
    resolves to two addresses, so each unanswered probe costs about four --
    `aihwbench runtimes` spent 16 of its 24 seconds waiting for four servers
    that were not running.

    It is a TCP connect rather than a short HTTP timeout on purpose. Shortening
    the HTTP timeout would also cut off a server that *is* running and busy
    loading a model, reporting it as absent at the moment it is doing the most
    work. Accepting a connection is not something a loading server stops doing,
    so this separates "nothing is there" from "it is slow to answer" and leaves
    the real request its full patience.
    """
    parsed = urllib.parse.urlsplit(url if "//" in url else f"//{url}")
    host = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if not host:
        return False
    try:
        # create_connection resolves and tries each address, so a host that
        # answers on ::1 but not 127.0.0.1 is still found.
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


#: The one OpenVINO Core for this process, built on first use.
_openvino_core: Any = None


def openvino_core() -> Any:
    """The process's OpenVINO `Core`, or None when OpenVINO is not installed.

    One Core, deliberately. Constructing one is free -- about a millisecond --
    but the first `get_available_devices()` on each costs around 900ms on the
    reference machine, because that is where the GPU plugins initialise. A
    fresh Core per call pays it every time: measured at roughly 220ms per
    `detect()` afterwards, in two backends, on every `aihwbench detect`,
    `runtimes` and `doctor`.

    Two module-level caches would not have fixed it. The cost is per Core, so
    the `openvino` and `openvino_genai` backends each keeping their own would
    still enumerate twice; it has to be one Core for the process.

    Held for the process lifetime, which means a device attached or disabled
    mid-run is not noticed. That is the right trade for a CLI that runs for
    seconds: re-enumerating on every detection to catch a GPU being unplugged
    during a benchmark buys nothing anyone needs.
    """
    global _openvino_core
    if _openvino_core is None:
        try:
            import openvino as ov

            _openvino_core = ov.Core()
        except Exception:  # noqa: BLE001 - not installed, or no usable runtime
            return None
    return _openvino_core


def openvino_devices() -> list[str]:
    """Devices visible to OpenVINO; empty when it is unavailable."""
    core = openvino_core()
    if core is None:
        return []
    try:
        return list(core.get_available_devices())
    except Exception:  # noqa: BLE001 - detection must never raise
        return []


def resolved_device(name: str | None) -> str | None:
    """Map what actually ran to the device vocabulary results record.

    `runtime.device` is in the comparison-safety classifier's strict set, and
    it used to hold whatever the caller typed. Two runs on the same silicon
    were therefore NOT_COMPARABLE when one passed `--device cpu` and the other
    took the `auto` default -- a split created by how someone spelled a flag,
    which is exactly the false distinction the classifier exists to avoid
    making.

    Returns None for a name this cannot map, so the caller falls back to the
    requested value rather than recording a guess.
    """
    if not name:
        return None
    key = name.strip().lower()
    if key in _RESOLVED_DEVICE_NAMES:
        return _RESOLVED_DEVICE_NAMES[key]
    # OpenVINO enumerates devices as GPU.0, GPU.1, NPU.0 and so on. The
    # ordinal identifies which card, and `system.gpu` already records that;
    # keeping it here would split two runs on one machine's only GPU.
    head = key.split(".", 1)[0]
    return _RESOLVED_DEVICE_NAMES.get(head)


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
        shape = [
            int(d) if isinstance(d, int) and not isinstance(d, bool) and d > 0 else 1
            for d in declared_shape
        ]
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
