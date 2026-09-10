"""Shared client for runtimes that serve an OpenAI-compatible HTTP API.

vLLM and SGLang both speak the same wire protocol, and so does LM Studio.
Writing that streaming loop once per backend would mean three places to fix
when a detail is wrong -- and the details here are exactly the kind that go
wrong quietly. Time-to-first-token measured from the wrong event, or token
counts taken from a chunk instead of the usage object, produces a plausible
number rather than an error.

What this measures, and does not
--------------------------------
These servers report token *counts* but no engine evaluation timers, so
generation tok/s here is usage tokens over the client's measured decode
window. That is a different quantity from an engine counter: it includes the
HTTP stack and the client's own scheduling. It is labelled
``client_wall_clock`` in ``metrics.metric_source`` and must never be presented
as an engine figure -- which is also the more honest number for this project,
since it is what a user of a local server actually waits.
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

__all__ = [
    "OpenAIServer",
    "chat_stream",
    "detect_server",
    "list_models",
    "metric_source_block",
    "run_openai_benchmark",
]


class OpenAIServer:
    """Connection details for one OpenAI-compatible server."""

    def __init__(
        self,
        name: str,
        host: str,
        *,
        backend_id: str,
        install_hint: str,
        model_format: str = "unknown",
    ) -> None:
        self.name = name
        self.host = host.rstrip("/")
        self.backend_id = backend_id
        self.install_hint = install_hint
        self.model_format = model_format


def _api_get(server: OpenAIServer, path: str, timeout: float = 5.0) -> Any | None:
    try:
        with urllib.request.urlopen(f"{server.host}{path}", timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, json.JSONDecodeError):
        return None


def server_version(server: OpenAIServer) -> str | None:
    """Server version where the runtime exposes one, else None.

    vLLM serves `/version`; SGLang does not. A runtime that cannot report its
    version gets null rather than a guess, because `runtime.version` moves a
    comparison from strictly to conditionally comparable and inventing one
    would hide a real difference.
    """
    data = _api_get(server, "/version")
    if isinstance(data, dict):
        version = data.get("version")
        if isinstance(version, str) and version:
            return version
    return None


def detect_server(server: OpenAIServer) -> BackendInfo:
    """Detect a running server by listing its models."""
    data = _api_get(server, "/v1/models")
    if isinstance(data, dict) and "data" in data:
        models = [m.get("id") for m in data.get("data", []) if m.get("id")]
        loaded = ", ".join(str(m) for m in models[:3]) or "none"
        return BackendInfo(
            server.name,
            RuntimeStatus.AVAILABLE,
            server_version(server),
            f"OpenAI-compatible server at {server.host} (serving: {loaded})",
        )
    return BackendInfo(
        server.name,
        RuntimeStatus.NOT_INSTALLED,
        None,
        server.install_hint,
    )


def list_models(server: OpenAIServer) -> list[str]:
    """Model ids the server is currently serving (empty if unreachable)."""
    data = _api_get(server, "/v1/models")
    if not isinstance(data, dict):
        return []
    return [str(m.get("id", "")) for m in data.get("data", []) if m.get("id")]


def chat_stream(
    server: OpenAIServer,
    model: str,
    prompt: str,
    config: BenchmarkConfig,
) -> dict[str, Any]:
    """One streamed chat completion, returning per-iteration measurements."""
    payload: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": True,
        "stream_options": {"include_usage": True},
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
    }
    # Not every server accepts `seed`, and one that rejects the whole request
    # over it would look like a benchmark failure. Sent because determinism is
    # worth having; the fidelity probe reports whether it was honoured.
    if config.seed is not None:
        payload["seed"] = config.seed

    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{server.host}/v1/chat/completions",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    ttft_ms: float | None = None
    usage: dict[str, Any] = {}
    # Arrival time of every content chunk, and the text. The runner needs the
    # first for the inter-token latency distribution and the second for the
    # output fingerprint; it strips both before publishing.
    chunk_times_ms: list[float] = []
    text_parts: list[str] = []

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
                try:
                    chunk = json.loads(data_str)
                except json.JSONDecodeError as exc:
                    raise BackendError(
                        f"{server.name} sent a malformed stream chunk: {exc}"
                    ) from exc
                choices = chunk.get("choices") or []
                content = choices[0].get("delta", {}).get("content") if choices else None
                if content:
                    now = (time.perf_counter() - start) * 1000.0
                    if ttft_ms is None:
                        ttft_ms = now
                    chunk_times_ms.append(now)
                    text_parts.append(content)
                # The usage object arrives in its own final chunk when
                # `include_usage` is set. Counting deltas instead would count
                # chunks, which are not tokens.
                if chunk.get("usage"):
                    usage = chunk["usage"]
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise BackendError(f"{server.name} API error {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise BackendError(f"Cannot reach {server.name} at {server.host}: {exc.reason}") from exc

    total_ms = (time.perf_counter() - start) * 1000.0
    if ttft_ms is None:
        raise BackendError(
            f"{server.name} stream produced no content tokens; check that "
            f"{model!r} is loaded and the prompt was accepted"
        )

    completion_tokens = usage.get("completion_tokens")
    prompt_tokens = usage.get("prompt_tokens")
    # The decode window is measured, not reported by the engine. Left null
    # when the server withheld token counts, because tok/s computed against an
    # unknown numerator would be a number with no meaning.
    eval_seconds: float | None = None
    if completion_tokens:
        eval_seconds = max((total_ms - ttft_ms) / 1000.0, 0.0)

    return {
        "ttft_ms": round(ttft_ms, 2),
        "total_latency_ms": round(total_ms, 2),
        "completion_tokens": completion_tokens,
        "eval_seconds": eval_seconds,
        "prompt_tokens": prompt_tokens,
        # These servers do not separate prompt evaluation from the wait for
        # the first token, and TTFT already includes queueing.
        "prompt_eval_seconds": None,
        "chunk_times_ms": [round(t, 3) for t in chunk_times_ms],
        "text": "".join(text_parts),
    }


def metric_source_block(server: OpenAIServer) -> dict[str, Any]:
    """Metric provenance: which figures are engine counters and which are not."""
    return {
        "completion_tokens": "engine_usage",
        "generation_tokens_per_second": "client_wall_clock",
        "ttft_ms": "client_wall_clock",
        "note": (
            f"{server.name} exposes no engine evaluation duration over its "
            "OpenAI-compatible API; tok/s divides usage-token counts by the "
            "measured wall-clock decode window, which includes the HTTP stack. "
            "This is what a client of a local server waits, and is not "
            "comparable with an in-process engine counter such as "
            "llama-bench's."
        ),
    }


def run_openai_benchmark(
    server: OpenAIServer,
    config: BenchmarkConfig,
    system: dict[str, Any],
) -> dict[str, Any]:
    """Execute a full benchmark against an OpenAI-compatible server."""
    info = detect_server(server)
    if info.status is not RuntimeStatus.AVAILABLE:
        raise BackendError(f"{server.name} is not available: {info.status.value} ({info.detail})")

    available = list_models(server)
    if available and config.model not in available:
        raise BackendError(
            f"Model {config.model!r} is not served by {server.name}. "
            f"Serving: {', '.join(available)}"
        )

    from ..metrics import aggregate_iteration_metrics, performance_per_watt
    from ..versions import CURRENT_SCHEMA_VERSION

    sampler = TelemetrySampler(interval_seconds=0.5)
    sampler.start()
    iterations: list[dict[str, Any]] = []
    try:
        for _ in range(config.warmup_runs):
            chat_stream(server, config.model, config.prompt, config)
        for _ in range(config.iterations):
            iterations.append(chat_stream(server, config.model, config.prompt, config))
    finally:
        sampler.stop()

    metrics = aggregate_iteration_metrics(iterations)
    telemetry = sampler.summary()
    metrics.update(telemetry)
    metrics["performance_per_watt"] = performance_per_watt(
        metrics["generation_tokens_per_second"], telemetry.get("average_power_watts")
    )
    metrics["metric_source"] = metric_source_block(server)

    return {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "run_id": new_run_id(server.name),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "system": system,
        "runtime": {
            "name": server.name,
            "version": info.version,
            "backend": server.backend_id,
            "device": config.device,
        },
        "model": {
            "name": config.model,
            "format": server.model_format,
            "quantization": None,
            "parameters": None,
            "checksum": None,
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
            "command": (f"aihwbench benchmark --runtime {server.name} --model {config.model}"),
        },
        "iterations": iterations,
    }
