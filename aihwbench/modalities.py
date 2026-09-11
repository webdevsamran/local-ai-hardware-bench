"""Non-text modalities: what each one measures, and why tok/s does not fit.

Everything else in this project measures tokens per second. None of these do,
and forcing them into that shape is how modality benchmarks come to report
numbers nobody can act on.

- **Embedding** is throughput per *text*, and it is dominated by batching. A
  single-text latency figure describes a use nobody has; the interesting
  number is how throughput scales with batch size, because that is what a
  retrieval pipeline actually does.
- **Reranking** is the same shape, per query-document pair.
- **Vision-language** splits into encoding the image and prefilling the text.
  One figure hides which half a slow machine is slow at, and they scale with
  different things — image resolution against prompt length.
- **ASR** is measured as a real-time factor: seconds of audio processed per
  second of wall clock. Tokens per second is meaningless when the input is a
  waveform.
- **TTS** is the inverse real-time factor plus time to first audio, which is
  what a user perceives.
- **Image generation** is seconds per image at a stated resolution and step
  count, all three of which have to travel together or the number means
  nothing.
- **Speech-to-speech** is round-trip latency across a chain, and its useful
  form is the per-stage breakdown: a slow chain is slow in one place.

Each modality here declares what it measures and what it needs. Where the
runtime is present the measurement runs; where it is not, detection says which
piece is missing rather than reporting the modality as unsupported.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

__all__ = [
    "MODALITIES",
    "modality_inventory",
    "measure_embedding_throughput",
    "DEFAULT_EMBED_BATCHES",
]

#: What each modality reports, so a consumer never reads one as tokens/second.
MODALITIES: dict[str, dict[str, Any]] = {
    "embedding": {
        "unit": "texts per second",
        "primary_axis": "batch_size",
        "why": (
            "throughput is dominated by batching; a single-text latency describes a use nobody has"
        ),
        "needs": "an embedding model (e.g. nomic-embed-text) on a runtime with an embed endpoint",
    },
    "reranker": {
        "unit": "query-document pairs per second",
        "primary_axis": "candidates_per_query",
        "why": "rerankers are called with a candidate list, and cost scales with its length",
        "needs": "a reranking model and a runtime exposing a rerank endpoint",
    },
    "vision_language": {
        "unit": "milliseconds, split into image encode and text prefill",
        "primary_axis": "image_resolution",
        "why": (
            "one combined figure hides which half is slow, and the halves scale "
            "with different inputs"
        ),
        "needs": "a vision-language model and a multimodal runtime (llama-mtmd-cli or equivalent)",
    },
    "asr": {
        "unit": "real-time factor (audio seconds per wall-clock second)",
        "primary_axis": "audio_duration",
        "why": "the input is a waveform, so tokens per second has no meaning",
        "needs": "whisper.cpp or an equivalent ASR runtime, and an audio file",
    },
    "tts": {
        "unit": "inverse real-time factor, plus time to first audio",
        "primary_axis": "text_length",
        "why": "what a user perceives is when sound starts, not when it finishes",
        "needs": "a TTS model (llama-tts with an OuteTTS-style GGUF, or Piper)",
    },
    "image_generation": {
        "unit": "seconds per image",
        "primary_axis": "steps",
        "why": (
            "seconds per image is meaningless without the resolution and step "
            "count beside it, and the three must travel together"
        ),
        "needs": "stable-diffusion.cpp or an equivalent local image runtime",
    },
    "speech_to_speech": {
        "unit": "round-trip milliseconds, broken down per stage",
        "primary_axis": "utterance_duration",
        "why": "a slow chain is slow in one place, and the total does not say which",
        "needs": "an ASR runtime, a generative model and a TTS runtime",
    },
}

#: Batch sizes that show the shape of the curve without taking long.
#:
#: Measured here: 8 texts took 256 ms and 32 took 238 ms, so throughput went
#: from 31 to 135 texts per second while wall time barely moved. A benchmark
#: that only measured batch 1 would have reported a rate 100x too low for how
#: anyone actually embeds.
DEFAULT_EMBED_BATCHES: tuple[int, ...] = (1, 8, 32, 64)

_OLLAMA_HOST = "http://localhost:11434"


def _embed_once(model: str, texts: list[str], host: str, timeout: float) -> tuple[float, Any]:
    request = urllib.request.Request(
        f"{host}/api/embed",
        data=json.dumps({"model": model, "input": texts}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return time.perf_counter() - started, payload


def measure_embedding_throughput(
    model: str,
    batch_sizes: tuple[int, ...] = DEFAULT_EMBED_BATCHES,
    text: str = "The quick brown fox jumps over the lazy dog. " * 4,
    host: str = _OLLAMA_HOST,
    warmup: bool = True,
    timeout: float = 300.0,
) -> dict[str, Any]:
    """Texts embedded per second, across batch sizes.

    A warm-up call is made first and discarded. Without it the first
    measurement carries the model load: the first embed here took 33.8 seconds
    against 0.24 for the same work warm, which would have been reported as the
    embedding rate.
    """
    if warmup:
        try:
            _embed_once(model, [text], host, timeout)
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
            return {
                "model": model,
                "batches": [],
                "unresolved": f"the embedding endpoint could not be reached: {exc}",
            }

    dimensions: int | None = None
    rows: list[dict[str, Any]] = []
    for size in batch_sizes:
        try:
            elapsed, payload = _embed_once(model, [text] * size, host, timeout)
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
            rows.append({"batch_size": size, "texts_per_second": None, "error": str(exc)})
            continue
        vectors = payload.get("embeddings") or []
        if dimensions is None and vectors:
            dimensions = len(vectors[0])
        rows.append(
            {
                "batch_size": size,
                "elapsed_ms": round(elapsed * 1000, 1),
                "texts_per_second": round(size / elapsed, 2) if elapsed > 0 else None,
                "returned_vectors": len(vectors),
                "error": None,
            }
        )

    measured = [r for r in rows if r.get("texts_per_second")]
    best = max(measured, key=lambda r: r["texts_per_second"]) if measured else None
    single = next((r for r in measured if r["batch_size"] == 1), None)
    return {
        "model": model,
        "unit": MODALITIES["embedding"]["unit"],
        "dimensions": dimensions,
        "batches": rows,
        "best_batch_size": best["batch_size"] if best else None,
        "best_texts_per_second": best["texts_per_second"] if best else None,
        # The number that says whether batching is worth arranging for.
        "batching_speedup": (
            round(best["texts_per_second"] / single["texts_per_second"], 1)
            if best and single and single["texts_per_second"]
            else None
        ),
        "caveat": (
            "measured against one runtime's batching, not the model's peak. A "
            "server that batches across concurrent requests will reach this "
            "without the caller batching anything."
        ),
        "unresolved": None if measured else "no batch size produced a measurement",
    }


def modality_inventory(host: str = _OLLAMA_HOST) -> dict[str, Any]:
    """Which modalities this machine can currently measure, and what is missing.

    Detection is by capability rather than by model name: Ollama reports what a
    model can do, and guessing from a name would claim embedding support for
    anything called `-embed`.
    """
    from .backends.llama_cpp import _find_binary

    available: dict[str, Any] = {}

    embed_models: list[str] = []
    try:
        with urllib.request.urlopen(f"{host}/api/tags", timeout=10.0) as response:
            for entry in json.loads(response.read().decode("utf-8")).get("models", []):
                name = entry.get("name", "")
                if name:
                    embed_models.append(name)
    except (urllib.error.URLError, OSError, json.JSONDecodeError):
        embed_models = []

    def _capable(model: str, capability: str) -> bool:
        request = urllib.request.Request(
            f"{host}/api/show",
            data=json.dumps({"model": model}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=20.0) as response:
                document = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, json.JSONDecodeError):
            return False
        return capability in (document.get("capabilities") or [])

    for name, spec in MODALITIES.items():
        entry = {**spec, "measurable": False, "missing": spec["needs"]}
        if name == "embedding":
            models = [m for m in embed_models if _capable(m, "embedding")]
            if models:
                entry.update(measurable=True, missing=None, models=models)
        elif name == "vision_language":
            models = [m for m in embed_models if _capable(m, "vision")]
            multimodal = _find_binary("llama-mtmd-cli")
            if models or multimodal:
                entry.update(
                    measurable=bool(models),
                    missing=None if models else "a vision model; the runtime is present",
                    models=models,
                    runtime=multimodal,
                )
        elif name == "tts":
            binary = _find_binary("llama-tts")
            if binary:
                entry.update(
                    measurable=False,
                    missing="a TTS model; the llama-tts runtime is present",
                    runtime=binary,
                )
        elif name == "asr":
            binary = _find_binary("whisper-cli") or _find_binary("main")
            if binary:
                entry.update(missing="an audio file; a whisper runtime is present", runtime=binary)
        available[name] = entry

    return {
        "modalities": available,
        "note": (
            "Each modality reports its own unit. None of them is tokens per "
            "second, and a consumer that reads them as such will compare a "
            "real-time factor against a generation rate."
        ),
    }
