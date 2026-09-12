"""ExLlamaV2 backend — EXL2 quantization, which is not GGUF and does not mix.

ExLlamaV2 is the fastest path for consumer NVIDIA cards on many models, and it
earns a backend for a reason beyond speed: EXL2 supports *fractional* bits per
weight. A 4.65 bpw quantization has no GGUF equivalent, so "llama.cpp at
q4_K_M against ExLlamaV2 at 4.65 bpw" is not like-for-like — and the
comparison-safety classifier cannot tell from the quantization strings alone,
because neither string is wrong.

So this backend records the bits per weight it actually ran and declares EXL2
as its own model format rather than mapping it onto the GGUF vocabulary. A
result labelled `q4` that was really 4.65 bpw would understate its memory and
overstate the quality of every GGUF result compared against it.

Needs a CUDA GPU, PyTorch and the `exllamav2` package. None is installed here,
so this detects and says which is missing rather than pretending.

**Written, not observed.** The generation path targets ExLlamaV2's dynamic
generator API and has never run: no NVIDIA machine with EXL2 weights has been
available to this project. The imports are deliberately narrow so a version
whose API has moved fails at load with a clear message rather than part-way
through a measurement.
"""

from __future__ import annotations

import importlib.util
import time
from pathlib import Path
from typing import Any

from .base import BackendError, BackendInfo, BenchmarkConfig, RuntimeStatus, new_run_id


def _installed(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):  # pragma: no cover - malformed install
        return False


def detect() -> BackendInfo:
    """Report which prerequisite is missing, not merely that one is."""
    has_torch = _installed("torch")
    has_exllama = _installed("exllamav2")

    if has_exllama and has_torch:
        try:
            import torch

            if not torch.cuda.is_available():
                return BackendInfo(
                    "exllamav2",
                    RuntimeStatus.HARDWARE_REQUIRED,
                    None,
                    "exllamav2 and torch are installed but torch reports no CUDA "
                    "device. ExLlamaV2 has no CPU path.",
                )
            version = getattr(importlib.import_module("exllamav2"), "__version__", None)
            return BackendInfo("exllamav2", RuntimeStatus.AVAILABLE, version)
        except Exception as exc:  # pragma: no cover - import failures vary
            return BackendInfo("exllamav2", RuntimeStatus.CONFIGURATION_REQUIRED, None, str(exc))

    missing = [
        name for name, present in (("torch", has_torch), ("exllamav2", has_exllama)) if not present
    ]
    return BackendInfo(
        "exllamav2",
        RuntimeStatus.NOT_INSTALLED,
        None,
        f"Missing: {', '.join(missing)}. Install a CUDA build of PyTorch and "
        "`pip install exllamav2`. It needs an NVIDIA GPU and EXL2-format "
        "weights, which are not interchangeable with GGUF.",
    )


def model_directory(config: BenchmarkConfig) -> Path:
    """The EXL2 weights directory, or a refusal naming a flag that exists."""
    raw = (config.extra or {}).get("model_path") or config.model
    if not raw:
        raise BackendError(
            "exllamav2 needs an EXL2 model directory: pass --model-path pointing "
            "at a folder of EXL2 weights (config.json plus .safetensors). A GGUF "
            "file is a different format and will not load."
        )
    directory = Path(str(raw))
    if directory.is_file():
        directory = directory.parent
    if not (directory / "config.json").is_file():
        raise BackendError(f"{directory} has no config.json, so it is not an EXL2 model directory")
    return directory


def bits_per_weight(model_dir: Path) -> float | None:
    """Bits per weight this quantization actually used.

    The reason this backend records it: EXL2 supports fractional bpw, so a 4.65
    bpw model has no GGUF equivalent and "q4" is not a synonym for it. The
    comparison-safety classifier compares quantization strings and cannot know
    that, which is what makes the number worth carrying explicitly.

    None when the model does not record it — unmeasured, never defaulted.
    """
    import json

    try:
        with open(model_dir / "config.json", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None
    quant = data.get("quantization_config")
    if isinstance(quant, dict):
        for key in ("bits", "bits_per_weight", "weight_bits"):
            value = quant.get(key)
            if isinstance(value, int | float) and not isinstance(value, bool):
                return float(value)
    return None


def _one_iteration(
    generator: Any, tokenizer: Any, job_class: Any, config: BenchmarkConfig
) -> dict[str, Any]:
    """One measured generation, shaped like every other LLM backend's.

    The keys are the ones `metrics.aggregate_iteration_metrics` reads, so this
    backend inherits the same interval, percentile and fidelity treatment as
    Ollama rather than a second interpretation that drifts from it.
    """
    input_ids = tokenizer.encode(config.prompt, add_bos=True)
    prompt_tokens = int(input_ids.shape[-1])

    job = job_class(
        input_ids=input_ids,
        max_new_tokens=config.max_tokens,
        decode_special_tokens=False,
    )
    generator.enqueue(job)

    chunk_times_ms: list[float] = []
    parts: list[str] = []
    generated = 0
    start = time.perf_counter()
    while generator.num_remaining_jobs():
        for result in generator.iterate():
            if result.get("stage") != "streaming":
                continue
            text = result.get("text")
            if text:
                chunk_times_ms.append((time.perf_counter() - start) * 1000.0)
                parts.append(text)
            token_ids = result.get("token_ids")
            if token_ids is not None:
                generated += int(token_ids.shape[-1])
    total_ms = (time.perf_counter() - start) * 1000.0

    ttft_ms = chunk_times_ms[0] if chunk_times_ms else None
    # Decode only, so tokens per second describes generation rather than the
    # whole request.
    eval_seconds = ((total_ms - ttft_ms) / 1000.0) if ttft_ms is not None else None

    return {
        "ttft_ms": round(ttft_ms, 2) if ttft_ms is not None else None,
        "total_latency_ms": round(total_ms, 2),
        "completion_tokens": generated or None,
        "eval_seconds": eval_seconds,
        "prompt_tokens": prompt_tokens,
        # The generator does not report prefill separately, and TTFT includes
        # the first token's decode. Left unmeasured rather than derived from a
        # figure that is not prefill.
        "prompt_eval_seconds": None,
        # Loading belongs to the model, not to an iteration; attached once by
        # run() so it is not counted five times.
        "load_time_ms": None,
        "chunk_times_ms": [round(t, 3) for t in chunk_times_ms],
        "text": "".join(parts),
    }


def run(config: BenchmarkConfig, system: dict[str, Any]) -> dict[str, Any]:
    """Benchmark an EXL2 model.

    Refuses when the prerequisites are absent rather than falling back: there
    is no CPU path, and a result labelled `exllamav2` produced by something
    else would be unattributable.
    """
    info = detect()
    if info.status is not RuntimeStatus.AVAILABLE:
        raise BackendError(f"exllamav2 is not available: {info.status.value} ({info.detail})")

    model_dir = model_directory(config)

    try:
        from exllamav2 import ExLlamaV2, ExLlamaV2Cache, ExLlamaV2Config, ExLlamaV2Tokenizer
        from exllamav2.generator import ExLlamaV2DynamicGenerator, ExLlamaV2DynamicJob
    except ImportError as exc:
        raise BackendError(
            "exllamav2 is installed but its dynamic generator API is not "
            f"importable ({exc}). This backend targets exllamav2 >= 0.1, where "
            "ExLlamaV2DynamicGenerator replaced the older streaming generator."
        ) from exc

    from ..metrics import aggregate_iteration_metrics, performance_per_watt
    from ..telemetry import TelemetrySampler
    from ..versions import CURRENT_SCHEMA_VERSION

    load_start = time.perf_counter()
    try:
        exl_config = ExLlamaV2Config(str(model_dir))
        exl_config.max_seq_len = config.context_length
        model = ExLlamaV2(exl_config)
        cache = ExLlamaV2Cache(model, lazy=True, max_seq_len=config.context_length)
        model.load_autosplit(cache, progress=False)
        tokenizer = ExLlamaV2Tokenizer(exl_config)
        generator = ExLlamaV2DynamicGenerator(model=model, cache=cache, tokenizer=tokenizer)
    except Exception as exc:  # noqa: BLE001 - surface loader errors cleanly
        raise BackendError(f"failed to load the EXL2 model at {model_dir}: {exc}") from exc
    load_time_ms = (time.perf_counter() - load_start) * 1000.0

    sampler = TelemetrySampler(interval_seconds=0.5)
    sampler.start()
    iterations: list[dict[str, Any]] = []
    try:
        for _ in range(config.warmup_runs):
            _one_iteration(generator, tokenizer, ExLlamaV2DynamicJob, config)
        for _ in range(config.iterations):
            iterations.append(_one_iteration(generator, tokenizer, ExLlamaV2DynamicJob, config))
    finally:
        sampler.stop()

    metrics = aggregate_iteration_metrics(iterations)
    telemetry = sampler.summary()
    metrics.update(telemetry)
    metrics["load_time_ms"] = round(load_time_ms, 2)
    metrics["performance_per_watt"] = performance_per_watt(
        metrics.get("generation_tokens_per_second"), telemetry.get("average_power_watts")
    )

    bpw = bits_per_weight(model_dir)
    return {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "run_id": new_run_id("exllamav2"),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "system": system,
        "runtime": {
            "name": "exllamav2",
            "version": info.version,
            "backend": "exllamav2-dynamic-generator",
            "device": "cuda",
            "device_requested": config.device,
        },
        "model": {
            "name": config.model or model_dir.name,
            "format": "exl2",
            # Its own format and its own precision vocabulary, on purpose. EXL2
            # bpw is a number rather than one of GGUF's named buckets, and
            # mapping 4.65 onto "q4" would make two incomparable runs look
            # comparable to a classifier that only sees strings.
            "quantization": (f"exl2-{bpw:g}bpw" if bpw is not None else None),
            "bits_per_weight": bpw,
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
            "command": f"aihwbench benchmark --runtime exllamav2 --model-path {model_dir}",
        },
        "iterations": iterations,
    }


#: Declared capability contract: truthful prerequisites.
CAPABILITIES: tuple[str, ...] = (
    "nvidia-gpu-required",
    "pytorch-cuda-required",
    "exl2-weights-required",
    "fractional-bits-per-weight",
    "not-comparable-with-gguf-quantization-labels",
)
