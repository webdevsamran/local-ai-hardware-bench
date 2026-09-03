"""Ollama backend — real benchmarking via the local Ollama HTTP API.

Detection: `ollama --version` and/or GET http://localhost:11434/api/version.
Benchmark: POST /api/generate with streaming enabled. Time-to-first-token
is measured from the first streamed response; token counts and evaluation
durations come from Ollama's final statistics object.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

from ..telemetry import TelemetrySampler
from .base import (
    BackendError,
    BackendInfo,
    BenchmarkConfig,
    RuntimeStatus,
    new_run_id,
    run_command,
)

OLLAMA_HOST = "http://localhost:11434"


def _api_get(path: str, timeout: float = 5.0) -> dict[str, Any] | None:
    try:
        with urllib.request.urlopen(f"{OLLAMA_HOST}{path}", timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data if isinstance(data, dict) else None
    except (urllib.error.URLError, OSError, json.JSONDecodeError):
        return None


def detect() -> BackendInfo:
    """Detect a locally installed Ollama runtime."""
    code, out = run_command(["ollama", "--version"], timeout=10.0)
    if code == 0 and out:
        # Output looks like "ollama version is 0.32.15"
        words = out.splitlines()[0].strip().split()
        version = words[-1] if words else out.splitlines()[0].strip()
        api = _api_get("/api/version")
        if api is None:
            return BackendInfo(
                "ollama",
                RuntimeStatus.CONFIGURATION_REQUIRED,
                version,
                "CLI installed but server not responding on localhost:11434",
            )
        return BackendInfo("ollama", RuntimeStatus.AVAILABLE, version)
    # CLI missing — maybe only the server is running.
    api = _api_get("/api/version")
    if api and "version" in api:
        return BackendInfo("ollama", RuntimeStatus.AVAILABLE, str(api["version"]))
    return BackendInfo(
        "ollama",
        RuntimeStatus.NOT_INSTALLED,
        None,
        "Install from https://ollama.com or via 'winget install Ollama.Ollama'",
    )


def list_models() -> list[str]:
    """Names of models available locally (empty if server unreachable)."""
    data = _api_get("/api/tags")
    if not data:
        return []
    return [m.get("name", "") for m in data.get("models", [])]


def model_digest(model: str) -> str | None:
    """Digest of a local model manifest (used as model checksum)."""
    data = _api_get("/api/tags")
    if not data:
        return None
    for m in data.get("models", []):
        if m.get("name") == model:
            digest: str | None = m.get("digest")
            return digest
    return None


def _generate_stream(model: str, prompt: str, config: BenchmarkConfig) -> dict[str, Any]:
    """One streaming generation. Returns measured per-iteration metrics."""
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": True,
        "options": {
            "num_predict": config.max_tokens,
            "temperature": config.temperature,
            "seed": config.seed,
            "num_ctx": config.context_length,
        },
    }
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{OLLAMA_HOST}/api/generate",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    ttft_ms: float | None = None
    start = time.perf_counter()
    final: dict[str, Any] = {}
    try:
        with urllib.request.urlopen(request, timeout=600) as resp:
            for raw_line in resp:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                chunk = json.loads(line)
                if ttft_ms is None and chunk.get("response"):
                    ttft_ms = (time.perf_counter() - start) * 1000.0
                if chunk.get("done"):
                    final = chunk
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise BackendError(f"Ollama API error {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise BackendError(f"Cannot reach Ollama server: {exc.reason}") from exc

    total_ms = (time.perf_counter() - start) * 1000.0
    if not final:
        raise BackendError("Ollama stream ended without a completion object")

    eval_count = final.get("eval_count")
    eval_duration_ns = final.get("eval_duration")
    prompt_count = final.get("prompt_eval_count")
    prompt_duration_ns = final.get("prompt_eval_duration")
    # Model-load time is only reported by Ollama on requests that actually
    # loaded the model (typically the first); when the model is already
    # resident the field is absent — that stays None, never an estimate (#5).
    load_duration_ns = final.get("load_duration")

    return {
        "ttft_ms": round(ttft_ms, 2) if ttft_ms is not None else None,
        "total_latency_ms": round(total_ms, 2),
        "completion_tokens": eval_count,
        "eval_seconds": (eval_duration_ns / 1e9) if eval_duration_ns else None,
        "prompt_tokens": prompt_count,
        "prompt_eval_seconds": (prompt_duration_ns / 1e9) if prompt_duration_ns else None,
        "load_time_ms": (round(load_duration_ns / 1e6, 2) if load_duration_ns else None),
    }


def run(config: BenchmarkConfig, system: dict[str, Any]) -> dict[str, Any]:
    """Execute a full benchmark and return a schema-1.0 result document."""
    info = detect()
    if info.status is not RuntimeStatus.AVAILABLE:
        raise BackendError(f"Ollama is not available: {info.status.value} ({info.detail})")

    available = list_models()
    if available and config.model not in available:
        raise BackendError(
            f"Model {config.model!r} not present locally. "
            f"Run: ollama pull {config.model}. Local models: {', '.join(available)}"
        )

    from ..metrics import aggregate_iteration_metrics
    from ..versions import CURRENT_SCHEMA_VERSION

    sampler = TelemetrySampler(interval_seconds=0.5)
    sampler.start()
    iterations: list[dict[str, Any]] = []
    try:
        for _ in range(config.warmup_runs):
            _generate_stream(config.model, config.prompt, config)
        for _ in range(config.iterations):
            iterations.append(_generate_stream(config.model, config.prompt, config))
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

    return {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "run_id": new_run_id("ollama"),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "system": system,
        "runtime": {
            "name": "ollama",
            "version": info.version,
            "backend": "ollama-http-api",
            "device": config.device,
        },
        "model": {
            "name": config.model,
            "format": "gguf",
            "quantization": None,
            "parameters": None,
            "checksum": model_digest(config.model),
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
            "command": f"aihwbench benchmark --runtime ollama --model {config.model}",
        },
        "iterations": iterations,
    }
