"""llama.cpp backend — real benchmarking via llama-server.

Detection: locate `llama-server` (or `llama-cli`) on PATH or common
install locations. Benchmark: start llama-server with the target GGUF
model, wait for its health endpoint, then issue streaming OpenAI-compatible
chat completions. TTFT is measured from the first streamed content chunk;
token counts come from the server's usage object (never estimated).
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from ..telemetry import TelemetrySampler
from .base import (
    BackendError,
    BackendInfo,
    BenchmarkConfig,
    RuntimeStatus,
    run_command,
    which,
)

_COMMON_DIRS = [
    Path("C:/llama.cpp"),
    Path(os.path.expanduser("~")) / "llama.cpp",
    Path("E:/llama.cpp"),
]


def _find_binary(name: str) -> str | None:
    found = which(name)
    if found:
        return found
    for directory in _COMMON_DIRS:
        for candidate in (directory / f"{name}.exe", directory / "build" / "bin" / "Release" / f"{name}.exe"):
            if candidate.is_file():
                return str(candidate)
    return None


def detect() -> BackendInfo:
    """Detect a locally installed llama.cpp runtime."""
    server = _find_binary("llama-server")
    if server is None:
        return BackendInfo(
            "llama.cpp", RuntimeStatus.NOT_INSTALLED, None,
            "Build from https://github.com/ggml-org/llama.cpp or download a CUDA release",
        )
    code, out = run_command([server, "--version"], timeout=15.0)
    version = None
    if code == 0 and out:
        for line in out.splitlines():
            if "version" in line.lower():
                version = line.strip()
                break
        if version is None:
            version = out.splitlines()[0].strip()
    return BackendInfo("llama.cpp", RuntimeStatus.AVAILABLE, version, server)


def _file_sha256(path: Path, chunk_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


class LlamaServerHandle:
    """Managed llama-server subprocess."""

    def __init__(self, binary: str, model_path: str, config: BenchmarkConfig, port: int = 8123) -> None:
        self.binary = binary
        self.model_path = model_path
        self.config = config
        self.port = port
        self.base_url = f"http://127.0.0.1:{port}"
        self.proc: subprocess.Popen[bytes] | None = None

    def __enter__(self) -> "LlamaServerHandle":
        cmd = [
            self.binary,
            "-m", self.model_path,
            "--port", str(self.port),
            "-c", str(self.config.context_length),
            "-ngl", "99" if self.config.device in ("auto", "cuda", "gpu") else "0",
            "--no-webui",
        ]
        self.proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        deadline = time.time() + 120
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise BackendError(f"llama-server exited early with code {self.proc.returncode}")
            try:
                with urllib.request.urlopen(f"{self.base_url}/health", timeout=2.0) as resp:
                    if resp.status == 200:
                        return self
            except (urllib.error.URLError, OSError):
                pass
            time.sleep(0.5)
        self.__exit__(None, None, None)
        raise BackendError("llama-server did not become healthy within 120s")

    def __exit__(self, *exc: Any) -> None:
        if self.proc is not None and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()


def _chat_stream(handle: LlamaServerHandle, config: BenchmarkConfig) -> dict[str, Any]:
    """One streaming chat completion against llama-server."""
    payload = {
        "messages": [{"role": "user", "content": config.prompt}],
        "max_tokens": config.max_tokens,
        "temperature": config.temperature,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{handle.base_url}/v1/chat/completions",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    ttft_ms: float | None = None
    start = time.perf_counter()
    usage: dict[str, Any] = {}
    with urllib.request.urlopen(request, timeout=600) as resp:
        for raw_line in resp:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line.startswith("data:"):
                continue
            data_str = line[5:].strip()
            if data_str == "[DONE]":
                break
            chunk = json.loads(data_str)
            if ttft_ms is None:
                choices = chunk.get("choices") or []
                if choices and (choices[0].get("delta") or {}).get("content"):
                    ttft_ms = (time.perf_counter() - start) * 1000.0
            if chunk.get("usage"):
                usage = chunk["usage"]
    total_ms = (time.perf_counter() - start) * 1000.0
    return {
        "ttft_ms": round(ttft_ms, 2) if ttft_ms is not None else None,
        "total_latency_ms": round(total_ms, 2),
        "completion_tokens": usage.get("completion_tokens"),
        "prompt_tokens": usage.get("prompt_tokens"),
        # llama.cpp usage does not include eval durations; tok/s is derived
        # downstream only when both count and duration exist.
        "eval_seconds": None,
        "prompt_eval_seconds": None,
    }


def run(config: BenchmarkConfig, system: dict[str, Any]) -> dict[str, Any]:
    """Execute a full llama.cpp benchmark. Requires a local GGUF path."""
    info = detect()
    if info.status is not RuntimeStatus.AVAILABLE:
        raise BackendError(f"llama.cpp is not available: {info.status.value} ({info.detail})")

    model_path = config.extra.get("model_path")
    if not model_path or not Path(model_path).is_file():
        raise BackendError(
            "llama.cpp backend requires --model-path pointing to a local .gguf file"
        )

    from .. import SCHEMA_VERSION
    from ..metrics import aggregate_iteration_metrics

    checksum = _file_sha256(Path(model_path))
    handle = LlamaServerHandle(info.detail or "llama-server", str(model_path), config)
    sampler = TelemetrySampler(interval_seconds=0.5)
    sampler.start()
    iterations: list[dict[str, Any]] = []
    try:
        with handle:
            for _ in range(config.warmup_runs):
                _chat_stream(handle, config)
            for _ in range(config.iterations):
                iterations.append(_chat_stream(handle, config))
    finally:
        sampler.stop()

    metrics = aggregate_iteration_metrics(iterations)
    metrics.update(sampler.summary())

    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": f"llamacpp-{int(time.time())}",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "system": system,
        "runtime": {
            "name": "llama.cpp",
            "version": info.version,
            "backend": "llama-server",
            "device": config.device,
        },
        "model": {
            "name": Path(model_path).name,
            "format": "gguf",
            "quantization": None,
            "parameters": None,
            "checksum": f"sha256:{checksum}",
        },
        "metrics": metrics,
        "reproducibility": {
            "prompt": config.prompt,
            "max_tokens": config.max_tokens,
            "temperature": config.temperature,
            "seed": config.seed,
            "context_length": config.context_length,
            "warmup_runs": config.warmup_runs,
            "iterations": config.iterations,
            "command": (
                f"aihwbench benchmark --runtime llama.cpp --model-path {model_path}"
            ),
        },
        "iterations": iterations,
    }