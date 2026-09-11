"""Ollama backend — real benchmarking via the local Ollama HTTP API.

Detection: `ollama --version` and/or GET http://localhost:11434/api/version.
Benchmark: POST /api/generate with streaming enabled. Time-to-first-token
is measured from the first streamed response; token counts and evaluation
durations come from Ollama's final statistics object.
"""

from __future__ import annotations

import json
import re
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


#: Ollama names blob files for their own content hash, so the digest can be
#: read out of a path without trusting (or keeping) the rest of the path.
_BLOB_SHA256 = re.compile(r"sha256[:-]([0-9a-f]{64})")


def _api_get(path: str, timeout: float = 5.0) -> dict[str, Any] | None:
    try:
        with urllib.request.urlopen(f"{OLLAMA_HOST}{path}", timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data if isinstance(data, dict) else None
    except (urllib.error.URLError, OSError, json.JSONDecodeError):
        return None


def _api_show(model: str, timeout: float = 20.0) -> dict[str, Any] | None:
    """The /api/show document for one model, or None if it cannot be read."""
    request = urllib.request.Request(
        f"{OLLAMA_HOST}/api/show",
        data=json.dumps({"model": model}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data if isinstance(data, dict) else None
    except (urllib.error.URLError, OSError, json.JSONDecodeError):
        return None


def model_weights_digest(model: str) -> str | None:
    """SHA-256 of the weights blob, as distinct from the manifest digest.

    `model_digest` returns what `/api/tags` calls the digest, which hashes the
    Ollama *manifest*: the weights layer plus the template plus the system
    prompt. Two Ollama models with identical weights and different templates
    have different manifest digests, and a llama.cpp run over the very same
    weights file records a third, unrelated-looking value. The zoo needs the
    one hash that means "these are the same weights".

    Ollama states it in the `FROM` line of `/api/show`, which names the blob
    file -- and blob files are named for their own content hash. Only the
    digest is extracted: the rest of that line is an absolute path through a
    home directory, which is exactly what `sanitize` exists to keep out of
    published results.
    """
    doc = _api_show(model)
    if not doc:
        return None
    modelfile = doc.get("modelfile")
    if not isinstance(modelfile, str):
        return None
    for line in modelfile.splitlines():
        if not line.strip().upper().startswith("FROM"):
            continue
        match = _BLOB_SHA256.search(line)
        if match:
            return match.group(1)
    return None


def model_license(model: str) -> dict[str, Any]:
    """Licence terms as Ollama reports them for a model.

    Taken from `model_info`, which relays the GGUF header's own
    `general.license`, so it agrees with `gguf.read_gguf_license` on the same
    weights. Never inferred from the model name.
    """
    doc = _api_show(model)
    info = (doc or {}).get("model_info") or {}
    spdx = info.get("general.license")
    link = info.get("general.license.link")
    return {
        "license": spdx if isinstance(spdx, str) and spdx else None,
        "license_link": link if isinstance(link, str) and link else None,
    }


def model_tokenizer(model: str) -> str | None:
    """Tokenizer identity as Ollama reports it.

    Built from the same header fields `gguf.read_gguf_tokenizer` uses, so the
    same weights measured through Ollama and through llama.cpp yield one
    identity. Ollama nulls the vocabulary array in its response, which is why
    the identity does not depend on it.
    """
    from ..gguf import tokenizer_identity

    doc = _api_show(model)
    return tokenizer_identity((doc or {}).get("model_info") or {})


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


def _model_entry(model: str) -> dict[str, Any] | None:
    """The /api/tags entry for one model, or None if it is not installed."""
    data = _api_get("/api/tags")
    if not data:
        return None
    for entry in data.get("models", []):
        if entry.get("name") == model:
            return entry if isinstance(entry, dict) else None
    return None


def model_digest(model: str) -> str | None:
    """Digest of a local model manifest (used as model checksum)."""
    entry = _model_entry(model)
    if entry is None:
        return None
    digest: str | None = entry.get("digest")
    return digest


def model_identity(model: str) -> dict[str, Any]:
    """Model identity from what Ollama reports, not from its tag.

    `quantization` and `parameters` were hardcoded to None while
    `/api/tags` had been returning `details.quantization_level` and
    `details.parameter_size` all along.

    `model.quantization` is in the comparison-safety classifier's strict set,
    so leaving it null meant two runs at different quantizations agreed about
    it -- `_same(None, None)` is True. With an Ollama tag the classifier still
    caught the difference through the name, because the tag happens to encode
    it; served under a name that does not, two different quantizations
    compared as STRICTLY_COMPARABLE with zero reasons.

    It also emptied the `quantization` command, whose whole purpose is
    grouping results by quantization, and the dashboard filter beside it.

    Parsed from the tag is what this deliberately does not do: `:latest` and a
    renamed model would both yield a confident wrong answer, and a wrong
    quantization is worse than a missing one.
    """
    entry = _model_entry(model)
    details = (entry or {}).get("details") or {}
    quantization = details.get("quantization_level")
    return {
        # Lower-cased to match the vocabulary the fit estimator and the
        # dashboard filter already use (`q4_k_m`, not `Q4_K_M`).
        "quantization": quantization.lower() if isinstance(quantization, str) else None,
        "parameters": details.get("parameter_size"),
        "family": details.get("family"),
        "format": details.get("format") or "gguf",
    }


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
    # Arrival time of every streamed chunk, and the text itself. The stream
    # previously read `response` only to detect the first token and dropped
    # both -- which left no way to measure the inter-token latency
    # distribution, and no way to tell whether a quantized run still produced
    # the same output.
    chunk_times_ms: list[float] = []
    text_parts: list[str] = []
    try:
        with urllib.request.urlopen(request, timeout=600) as resp:
            for raw_line in resp:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                chunk = json.loads(line)
                piece = chunk.get("response")
                if piece:
                    now = (time.perf_counter() - start) * 1000.0
                    if ttft_ms is None:
                        ttft_ms = now
                    chunk_times_ms.append(now)
                    text_parts.append(piece)
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
        # Consumed by the runner for the streaming-latency distribution and
        # the output-fidelity probe, then stripped: neither the raw text nor
        # a per-token timing array belongs in a published result.
        "chunk_times_ms": [round(t, 3) for t in chunk_times_ms],
        "text": "".join(text_parts),
    }


def generate_text(prompt: str, config: BenchmarkConfig) -> str:
    """One completion, returning only the text.

    The optional contract an agentic workload needs: it drives its own loop
    and supplies a different prompt each turn, so it needs a plain
    prompt-in/text-out call rather than the full measured benchmark path. A
    backend that does not implement this cannot run agentic workloads, which
    the CLI reports rather than silently skipping.
    """
    return str(_generate_stream(config.model, prompt, config).get("text") or "")


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

    from ..metrics import aggregate_iteration_metrics, cold_start_metrics
    from ..versions import CURRENT_SCHEMA_VERSION

    sampler = TelemetrySampler(interval_seconds=0.5)
    sampler.start()
    iterations: list[dict[str, Any]] = []
    warmups: list[dict[str, Any]] = []
    try:
        for _ in range(config.warmup_runs):
            # Warm-ups are excluded from the published metrics, but the first
            # one is the only cold-start measurement a run ever produces:
            # Ollama reports load_duration only when it actually loaded the
            # model. Discarding it outright threw away the number that answers
            # "how long before this is usable", which is a real part of the
            # experience and one throughput benchmarks ignore entirely.
            warmups.append(_generate_stream(config.model, config.prompt, config))
        for _ in range(config.iterations):
            iterations.append(_generate_stream(config.model, config.prompt, config))
    finally:
        sampler.stop()

    # Asked once, after the run: the model is certainly resident by now, and
    # a tag installed mid-run would describe the wrong thing.
    identity = model_identity(config.model)

    metrics = aggregate_iteration_metrics(iterations)
    metrics.update(cold_start_metrics(warmups, iterations))
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
            **identity,
            "checksum": model_digest(config.model),
            # In the classifier's strict set, and null in every result
            # published before this: a tokenizer change alters what a
            # token is, so tokens per second stops meaning the same thing.
            "tokenizer": model_tokenizer(config.model),
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
