"""llama.cpp backend — real benchmarking via llama-server.

Detection: locate `llama-server` (or `llama-cli`) on PATH or common
install locations. Benchmark: start llama-server on an OS-assigned free
port (or a caller-supplied one), wait for its health endpoint, then issue
streaming OpenAI-compatible chat completions. TTFT is measured from the
first streamed content chunk; token counts come ONLY from the server's
usage object — SSE chunks are transport-dependent (a chunk may carry
several tokens or a partial one) and are counted separately under
``stream_content_chunks``, never substituted for tokens.
"""

from __future__ import annotations

import json
import os
import re
import socket
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
    file_sha256,
    new_run_id,
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
        for candidate in (
            directory / f"{name}.exe",
            directory / "build" / "bin" / "Release" / f"{name}.exe",
        ):
            if candidate.is_file():
                return str(candidate)
    return None


def detect() -> BackendInfo:
    """Detect a locally installed llama.cpp runtime."""
    server = _find_binary("llama-server")
    if server is None:
        return BackendInfo(
            "llama.cpp",
            RuntimeStatus.NOT_INSTALLED,
            None,
            "Build from https://github.com/ggml-org/llama.cpp or download a CUDA release",
        )
    code, out = run_command([server, "--version"], timeout=15.0)
    version = None
    if code == 0 and out:
        # Expected format: "version: 0.2.0-dev (build 10578, commit 369e1cd61)"
        match = re.search(r"version:\s*(.+)", out)
        if match:
            version = match.group(1).strip()
        else:
            version = out.splitlines()[0].strip()
    return BackendInfo("llama.cpp", RuntimeStatus.AVAILABLE, version, server)


def _free_port() -> int:
    """Ask the OS for a free TCP port (avoids fixed-port collisions)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class LlamaServerHandle:
    """Managed llama-server subprocess."""

    def __init__(
        self, binary: str, model_path: str, config: BenchmarkConfig, port: int | None = None
    ) -> None:
        self.binary = binary
        self.model_path = model_path
        self.config = config
        self.port = port  # None -> OS-assigned free port at start
        self.proc: subprocess.Popen[bytes] | None = None

    def __enter__(self) -> LlamaServerHandle:
        if self.port is None:
            self.port = _free_port()
        self.base_url = f"http://127.0.0.1:{self.port}"
        cmd = [
            self.binary,
            "-m",
            self.model_path,
            "--port",
            str(self.port),
            "-c",
            str(self.config.context_length),
            "-ngl",
            "99" if self.config.device in ("auto", "cuda", "gpu") else "0",
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
        if self.proc is None:
            return
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=5)
        self.proc = None


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
    first_content_at: float | None = None
    last_content_at: float | None = None
    content_chunks = 0
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
            choices = chunk.get("choices") or []
            content = (choices[0].get("delta") or {}).get("content") if choices else None
            if content:
                now = time.perf_counter()
                if first_content_at is None:
                    first_content_at = now
                    ttft_ms = (now - start) * 1000.0
                last_content_at = now
                content_chunks += 1
            if chunk.get("usage"):
                usage = chunk["usage"]
    total_ms = (time.perf_counter() - start) * 1000.0

    # Token counts come ONLY from the server usage object. SSE content
    # chunks are transport-dependent (a chunk may carry several tokens or
    # a partial one) and are recorded separately for diagnostics only —
    # they are never substituted for tokens.
    completion_tokens = usage.get("completion_tokens")
    # Wall-clock streaming duration between first and last content chunk.
    stream_seconds = (
        (last_content_at - first_content_at)
        if first_content_at is not None and last_content_at is not None
        else None
    )
    return {
        "ttft_ms": round(ttft_ms, 2) if ttft_ms is not None else None,
        "total_latency_ms": round(total_ms, 2),
        "completion_tokens": completion_tokens,
        "prompt_tokens": usage.get("prompt_tokens"),
        "eval_seconds": stream_seconds,
        "prompt_eval_seconds": None,
        "stream_content_chunks": content_chunks,
    }


def metric_source_block() -> dict[str, Any]:
    """Metric provenance for llama.cpp results (never conflated).

    ``completion_tokens`` is a llama-server usage-object counter; tok/s is
    derived over the client wall-clock window between first and last
    streamed content chunk — labeled explicitly as client-derived.
    """
    return {
        "completion_tokens": "engine_usage",
        "generation_tokens_per_second": "client_wall_clock",
        "note": (
            "tokens counted by the llama-server usage object; tok/s derived "
            "over the client wall-clock window between first and last "
            "streamed content chunk"
        ),
    }


def run(config: BenchmarkConfig, system: dict[str, Any]) -> dict[str, Any]:
    """Execute a full llama.cpp benchmark. Requires a local GGUF path."""
    info = detect()
    if info.status is not RuntimeStatus.AVAILABLE:
        raise BackendError(f"llama.cpp is not available: {info.status.value} ({info.detail})")

    model_path = config.extra.get("model_path")
    if not model_path or not Path(model_path).is_file():
        raise BackendError("llama.cpp backend requires --model-path pointing to a local .gguf file")

    from ..metrics import aggregate_iteration_metrics
    from ..versions import CURRENT_SCHEMA_VERSION

    checksum = file_sha256(model_path)
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
    telemetry = sampler.summary()
    metrics.update(telemetry)
    # Recompute performance-per-watt now that measured power is available.
    from ..metrics import performance_per_watt

    metrics["performance_per_watt"] = performance_per_watt(
        metrics["generation_tokens_per_second"], telemetry.get("average_power_watts")
    )
    metrics["metric_source"] = metric_source_block()

    return {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "run_id": new_run_id("llamacpp"),
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
        "telemetry": sampler.provenance(),
        "reproducibility": {
            "prompt": config.prompt,
            "max_tokens": config.max_tokens,
            "temperature": config.temperature,
            "seed": config.seed,
            "context_length": config.context_length,
            "warmup_runs": config.warmup_runs,
            "iterations": config.iterations,
            "command": (f"aihwbench benchmark --runtime llama.cpp --model-path {model_path}"),
        },
        "iterations": iterations,
    }
