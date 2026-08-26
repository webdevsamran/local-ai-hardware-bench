"""LM Studio backend — benchmarking via its OpenAI-compatible local server.

Detection: GET http://localhost:1234/v1/models.
Benchmark: POST /v1/chat/completions with streaming. Time-to-first-token is
measured from the first streamed content delta. Token counts come from the
``usage`` object (requested via ``stream_options.include_usage``). LM Studio
does not expose evaluation durations, so engine-counter tok/s stay null —
never estimated.
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
)

LMSTUDIO_HOST = "http://localhost:1234"


def _api_get(path: str, timeout: float = 5.0) -> Any | None:
    try:
        with urllib.request.urlopen(f"{LMSTUDIO_HOST}{path}", timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, json.JSONDecodeError):
        return None


def detect() -> BackendInfo:
    """Detect a running LM Studio local server."""
    data = _api_get("/v1/models")
    if isinstance(data, dict) and "data" in data:
        count = len(data.get("data", []))
        return BackendInfo(
            "lmstudio",
            RuntimeStatus.AVAILABLE,
            None,
            f"OpenAI-compatible server on localhost:1234 ({count} model(s) loaded)",
        )
    return BackendInfo(
        "lmstudio",
        RuntimeStatus.NOT_INSTALLED,
        None,
        "Start the LM Studio local server (Developer tab, port 1234) or install from "
        "https://lmstudio.ai",
    )


def list_models() -> list[str]:
    """Model ids currently loaded in LM Studio (empty if unreachable)."""
    data = _api_get("/v1/models")
    if not isinstance(data, dict):
        return []
    return [str(m.get("id", "")) for m in data.get("data", []) if m.get("id")]


def _chat_stream(model: str, prompt: str, config: BenchmarkConfig) -> dict[str, Any]:
    """One streamed chat completion. Returns measured per-iteration metrics."""
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": True,
        "stream_options": {"include_usage": True},
        "temperature": config.temperature,
        "seed": config.seed,
        "max_tokens": config.max_tokens,
    }
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{LMSTUDIO_HOST}/v1/chat/completions",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    ttft_ms: float | None = None
    usage: dict[str, Any] = {}
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=600) as resp:
            for raw_line in resp:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                data_str = line[len("data:") :].strip()
                if data_str == "[DONE]":
                    break
                chunk = json.loads(data_str)
                choices = chunk.get("choices") or []
                content = choices[0].get("delta", {}).get("content") if choices else None
                if ttft_ms is None and content:
                    ttft_ms = (time.perf_counter() - start) * 1000.0
                if chunk.get("usage"):
                    usage = chunk["usage"]
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise BackendError(f"LM Studio API error {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise BackendError(f"Cannot reach LM Studio server: {exc.reason}") from exc

    total_ms = (time.perf_counter() - start) * 1000.0
    if ttft_ms is None:
        raise BackendError(
            "LM Studio stream produced no content tokens; check that the model is loaded"
        )

    # LM Studio does not report engine evaluation durations. Token counts come
    # from the usage object when provided; otherwise they stay null. The
    # decode window below is a *measured wall-clock lower bound*, not an
    # engine counter.
    completion_tokens = usage.get("completion_tokens")
    prompt_tokens = usage.get("prompt_tokens")
    eval_seconds: float | None = None
    prompt_eval_seconds: float | None = None
    if completion_tokens and ttft_ms is not None:
        eval_seconds = max((total_ms - ttft_ms) / 1000.0, 0.0)
    return {
        "ttft_ms": round(ttft_ms, 2),
        "total_latency_ms": round(total_ms, 2),
        "completion_tokens": completion_tokens,
        "eval_seconds": eval_seconds,
        "prompt_tokens": prompt_tokens,
        "prompt_eval_seconds": prompt_eval_seconds,
    }


def run(config: BenchmarkConfig, system: dict[str, Any]) -> dict[str, Any]:
    """Execute a full benchmark and return a schema-1.0 result document."""
    info = detect()
    if info.status is not RuntimeStatus.AVAILABLE:
        raise BackendError(f"LM Studio is not available: {info.status.value} ({info.detail})")

    available = list_models()
    if available and config.model not in available:
        raise BackendError(
            f"Model {config.model!r} not loaded in LM Studio. Loaded models: {', '.join(available)}"
        )

    from .. import SCHEMA_VERSION
    from ..metrics import aggregate_iteration_metrics, performance_per_watt

    sampler = TelemetrySampler(interval_seconds=0.5)
    sampler.start()
    iterations: list[dict[str, Any]] = []
    try:
        for _ in range(config.warmup_runs):
            _chat_stream(config.model, config.prompt, config)
        for _ in range(config.iterations):
            iterations.append(_chat_stream(config.model, config.prompt, config))
    finally:
        sampler.stop()

    metrics = aggregate_iteration_metrics(iterations)
    telemetry = sampler.summary()
    metrics.update(telemetry)
    metrics["performance_per_watt"] = performance_per_watt(
        metrics["generation_tokens_per_second"], telemetry.get("average_power_watts")
    )
    # Decode-window tok/s is derived only where the server reported real token
    # counts; it is a wall-clock measurement, never an estimate.
    if metrics.get("generation_tokens_per_second") is None:
        rates = [
            it["completion_tokens"] / it["eval_seconds"]
            for it in iterations
            if it.get("completion_tokens") and it.get("eval_seconds")
        ]
        if rates:
            metrics["generation_tokens_per_second"] = round(sum(rates) / len(rates), 2)

    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": new_run_id("lmstudio"),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "system": system,
        "runtime": {
            "name": "lmstudio",
            "version": info.version,
            "backend": "lmstudio-openai-api",
            "device": config.device,
        },
        "model": {
            "name": config.model,
            "format": "gguf",
            "quantization": None,
            "parameters": None,
            "checksum": None,
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
            "command": f"aihwbench benchmark --runtime lmstudio --model {config.model}",
        },
        "iterations": iterations,
    }
