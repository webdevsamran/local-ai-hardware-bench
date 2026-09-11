"""OpenVINO GenAI backend — measured LLM pipelines on Intel CPU, GPU and NPU.

This backend was detection-only for a long time: it could tell you OpenVINO
GenAI was installed and then refused to run, which was the honest thing to do
while no measured path existed. It measures now.

**Why it earns its place.** Every other LLM backend here targets one vendor's
silicon. OpenVINO runs the same IR on an Intel CPU, an Intel iGPU, an Intel
NPU -- and, on recent releases, a discrete GPU -- so it is the one runtime that
can put three devices in the same machine on the same footing, with the model
held constant. That is the comparison a buyer actually faces.

**Where the numbers come from.** The pipeline reports its own `PerfMetrics`:
time to first token, time per output token, token counts, load time. Those are
recorded, and so is the wall-clock view from a streaming callback, because they
measure different things and the difference is the point. The runtime's TTFT
stops when the model has produced a token; the caller's stops when the text
arrives, after detokenisation. Reporting only the first flatters the runtime;
reporting only the second hides where the time went.

**Why `--device auto` is refused.** OpenVINO's AUTO plugin picks a device at
compile time and `LLMPipeline` exposes no way to ask which one it picked --
`core.get_property("AUTO", "EXECUTION_DEVICES")` needs a compiled model this
API does not hand back. `runtime.device` is in the comparison-safety
classifier's strict set, so a result that guessed would be one this project
would then happily compare against a CPU run. An error naming the visible
devices is worth more than a result with a fabricated device field.

**Quantization is read, not inferred.** The IR carries NNCF's own record of how
the weights were compressed -- mode, group size, ratio -- in `rt_info`. A
filename saying "int4" is a claim by whoever named the directory; `int4_asym`
with `group_size=128` is what the compressor wrote down.
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

from .base import (
    BackendError,
    BackendInfo,
    BenchmarkConfig,
    BenchmarkMetadata,
    RuntimeStatus,
    file_sha256,
    new_run_id,
    openvino_core,
    openvino_devices,
)

METADATA = BenchmarkMetadata(
    name="openvino_genai",
    description="OpenVINO GenAI (LLM pipeline) on Intel CPU/GPU/NPU",
    capabilities=("llm", "openvino", "intel"),
)

#: The device vocabulary this project uses, mapped to OpenVINO's.
#: `auto` is deliberately absent -- see the module docstring.
_DEVICE_ALIASES = {
    "cpu": "CPU",
    "gpu": "GPU",
    "igpu": "GPU.0",
    "npu": "NPU",
}

#: The file the IR's weights live in, and the one worth hashing: the .xml is
#: topology and changes with the converter version, while the .bin is what
#: actually determines the numbers.
_WEIGHTS_FILE = "openvino_model.bin"
_TOPOLOGY_FILE = "openvino_model.xml"


def _import_openvino_genai() -> Any:
    try:
        import openvino_genai

        return openvino_genai
    except ImportError:
        return None


def _detect_devices() -> list[str]:
    """Visible OpenVINO devices (empty when the Core is unavailable)."""
    return openvino_devices()


def device_names() -> dict[str, str]:
    """Each visible device with the hardware it actually is.

    `GPU.1` says nothing; "NVIDIA GeForce RTX 3080 Ti Laptop GPU (dGPU)" is
    what belongs in a result someone else has to interpret.
    """
    core = openvino_core()
    if core is None:
        return {}
    names: dict[str, str] = {}
    for device in openvino_devices():
        try:
            names[device] = str(core.get_property(device, "FULL_DEVICE_NAME"))
        except Exception:  # noqa: BLE001 - a device that will not name itself
            names[device] = ""
    return names


def detect() -> BackendInfo:
    """Detect OpenVINO GenAI plus an Intel-visible device, honestly."""
    package = _import_openvino_genai()
    version = getattr(package, "__version__", None)
    if package is None:
        return BackendInfo(
            "openvino_genai",
            RuntimeStatus.CONFIGURATION_REQUIRED,
            None,
            "Install with 'pip install openvino-genai' to enable this backend",
        )
    devices = [d for d in _detect_devices() if d.startswith(("CPU", "GPU", "NPU"))]
    if not devices:
        return BackendInfo(
            "openvino_genai",
            RuntimeStatus.HARDWARE_REQUIRED,
            version,
            "No CPU/GPU/NPU device visible to OpenVINO",
        )
    return BackendInfo(
        "openvino_genai",
        RuntimeStatus.AVAILABLE,
        version,
        f"devices: {', '.join(devices)}",
    )


def list_models() -> list[str]:
    """No local model registry for GenAI pipelines; always empty."""
    return []


def resolve_device(requested: str, visible: list[str]) -> str:
    """The OpenVINO device string for `requested`, or raise.

    Raising on `auto` is the point of this function. See the module docstring:
    the plugin's choice is not observable through `LLMPipeline`, and a result
    whose device is a guess is worse than no result, because the classifier
    will compare it.
    """
    key = (requested or "").strip()
    lowered = key.lower()
    if lowered in {"", "auto"}:
        raise BackendError(
            "openvino_genai needs an explicit device: OpenVINO's AUTO plugin "
            "chooses at compile time and does not report which device it chose, "
            "so the result could not say what it ran on. "
            f"Visible devices: {', '.join(visible) or 'none'}. "
            "Pass --device cpu, --device gpu, --device npu, or an exact "
            "OpenVINO name such as GPU.0."
        )
    mapped = _DEVICE_ALIASES.get(lowered, key.upper() if lowered.startswith("gpu") else key)
    if mapped in visible:
        return mapped
    # `gpu` with several GPUs present: OpenVINO resolves bare GPU to GPU.0, but
    # say so rather than let the result imply a choice nobody made.
    if mapped == "GPU" and any(d.startswith("GPU.") for d in visible):
        return "GPU"
    raise BackendError(
        f"device {requested!r} is not visible to OpenVINO (visible: {', '.join(visible) or 'none'})"
    )


def model_provenance(model_dir: Path) -> dict[str, Any]:
    """How this IR was produced, read out of the IR.

    NNCF and optimum-intel both stamp their settings into `rt_info` at
    conversion time. That is a record made by the tool that did the work, which
    is worth more than the directory name -- "int4" in a path is somebody's
    label, `int4_asym` with `group_size=128` is what the compressor applied.
    Absent keys stay absent; nothing here is defaulted.
    """
    fields: dict[str, Any] = {}
    core = openvino_core()
    if core is None:
        return fields
    try:
        model = core.read_model(str(model_dir / _TOPOLOGY_FILE))
    except Exception:  # noqa: BLE001 - provenance is a bonus, never a blocker
        return fields

    def read(path: list[str]) -> str | None:
        try:
            value = model.get_rt_info(path)
        except Exception:  # noqa: BLE001 - key simply absent
            return None
        text = str(getattr(value, "value", value)).strip()
        return text or None

    mapping = {
        "quantization": ["nncf", "weight_compression", "mode"],
        "quantization_group_size": ["nncf", "weight_compression", "group_size"],
        "quantization_ratio": ["nncf", "weight_compression", "ratio"],
        "quantization_awq": ["nncf", "weight_compression", "awq"],
        "converted_by": ["optimum", "optimum_intel_version"],
        "ir_built_with_openvino": ["Runtime_version"],
    }
    for field, path in mapping.items():
        value = read(path)
        if value is not None:
            fields[field] = value
    return fields


def _tokenizer_identity(model_dir: Path) -> str | None:
    """A hash of the tokenizer, since a change to it changes what a token is.

    `runtime.tokenizer` is in the classifier's strict set for exactly this
    reason: tokens per second is not comparable across two models that
    disagree about what a token is.
    """
    for name in ("openvino_tokenizer.bin", "tokenizer.json"):
        candidate = model_dir / name
        if candidate.is_file():
            digest = file_sha256(str(candidate))
            return f"{name}:{digest}" if digest else None
    return None


def _generation_config(genai: Any, config: BenchmarkConfig) -> Any:
    """A GenerationConfig that matches what the result claims was run."""
    generation = genai.GenerationConfig()
    generation.max_new_tokens = config.max_tokens
    # Temperature 0 means greedy here, as everywhere else in this project.
    # Setting `temperature = 0.0` with sampling on is a different thing in
    # every runtime and comparable in none of them.
    if config.temperature and config.temperature > 0.0:
        generation.do_sample = True
        generation.temperature = config.temperature
        generation.rng_seed = config.seed
    else:
        generation.do_sample = False
    return generation


def _one_iteration(pipe: Any, genai: Any, config: BenchmarkConfig) -> dict[str, Any]:
    """One measured generation, shaped like every other LLM backend's.

    The keys are the ones `metrics.aggregate_iteration_metrics` reads, so this
    backend gets the same interval, percentile and fidelity treatment as Ollama
    rather than a second implementation that drifts from it.
    """
    chunk_times_ms: list[float] = []
    parts: list[str] = []
    start = time.perf_counter()

    def streamer(chunk: str) -> Any:
        chunk_times_ms.append((time.perf_counter() - start) * 1000.0)
        parts.append(chunk)
        return genai.StreamingStatus.RUNNING

    # A list, not a bare string: `generate("...")` returns a plain string and
    # drops `perf_metrics` entirely, which is a silent loss of every number the
    # runtime measured about itself.
    result = pipe.generate([config.prompt], _generation_config(genai, config), streamer=streamer)
    total_ms = (time.perf_counter() - start) * 1000.0

    perf = getattr(result, "perf_metrics", None)
    if perf is None:
        raise BackendError(
            "the pipeline returned no perf_metrics; refusing to publish "
            "timings this backend cannot attribute"
        )

    generated = perf.get_num_generated_tokens()
    prompt_tokens = perf.get_num_input_tokens()
    # Durations come back in milliseconds, as a mean/std over the request.
    inference_ms = perf.get_inference_duration().mean
    runtime_ttft_ms = perf.get_ttft().mean
    runtime_tpot_ms = perf.get_tpot().mean

    text = "".join(parts) or (result.texts[0] if getattr(result, "texts", None) else "")

    return {
        # What the caller experienced: the first chunk of text arriving. The
        # runtime's own figure is recorded beside it, not instead of it --
        # detokenisation sits between them and it is not free.
        "ttft_ms": round(chunk_times_ms[0], 2) if chunk_times_ms else None,
        "runtime_ttft_ms": round(runtime_ttft_ms, 2) if runtime_ttft_ms else None,
        "total_latency_ms": round(total_ms, 2),
        "completion_tokens": generated,
        # Decode time, as tokens x time-per-output-token.
        #
        # NOT `get_inference_duration()`, which counts every forward pass the
        # request made -- prefill included -- so dividing generated tokens by
        # it reports a rate for work that is partly not generation.
        #
        # The size of that matters less than the definition. Measured on the
        # reference machine's CPU: within about 1% either way when generation
        # dominates (33-token prompt, 64 generated), and 5% when it does not
        # (994-token prompt, 8 generated). Neither figure is pure decode --
        # TPOT is derived from the generate loop, so it carries sampling and
        # detokenisation with it -- but it is the one that answers "how fast
        # do tokens arrive" rather than "how much compute did the request
        # take". The total is kept below for anyone who wants the other.
        "eval_seconds": (
            (generated * runtime_tpot_ms / 1000.0) if generated and runtime_tpot_ms else None
        ),
        "runtime_inference_seconds": (inference_ms / 1000.0) if inference_ms else None,
        "prompt_tokens": prompt_tokens,
        # Prefill, approximated as TTFT minus one token's decode.
        #
        # TTFT is prefill *plus* producing the first token, so using it whole
        # would charge prefill for work it did not do and understate prompt
        # throughput. Subtracting one TPOT is not exact either -- the first
        # token is generally the slowest of the run -- but it is closer, and
        # the direction of the remaining error is known and stated rather than
        # silently folded into a published rate.
        "prompt_eval_seconds": (
            max(runtime_ttft_ms - runtime_tpot_ms, 0.0) / 1000.0 if runtime_ttft_ms else None
        ),
        # Load time belongs to the pipeline, not to an iteration; it is
        # attached once by `run()` so it is not counted five times.
        "load_time_ms": None,
        "runtime_tpot_ms": round(runtime_tpot_ms, 3),
        # Chunk arrivals, which is what the streamer can honestly report: one
        # chunk is not guaranteed to be one token, so this is a streaming
        # series rather than a per-token one -- the same thing Ollama's
        # streaming path produces, and read the same way downstream.
        "chunk_times_ms": [round(t, 3) for t in chunk_times_ms],
        "text": text,
    }


#: Compiled pipelines, keyed by the model and device they were built for.
#:
#: Compiling an IR takes 2 seconds on the CPU and 17 on a discrete GPU, and an
#: agentic workload calls `generate_text` once per turn. Rebuilding each time
#: would leave this backend nominally able to run those workloads and far too
#: slow to actually use -- the capability would exist and nobody could reach
#: it. Benchmarks are unaffected: `run()` compiles once by construction, and
#: measures the compile it does.
_PIPELINE_CACHE: dict[tuple[str, str], Any] = {}


def _pipeline_for(genai: Any, model_dir: Path, device: str) -> Any:
    key = (str(model_dir), device)
    cached = _PIPELINE_CACHE.get(key)
    if cached is None:
        cached = genai.LLMPipeline(str(model_dir), device)
        _PIPELINE_CACHE[key] = cached
    return cached


def generate_text(prompt: str, config: BenchmarkConfig) -> str:
    """One completion, returning only the text.

    The contract an agentic workload needs: it drives its own loop with a
    different prompt each turn.
    """
    genai = _import_openvino_genai()
    if genai is None:
        raise BackendError("openvino_genai is not installed")
    model_dir = _require_model_dir(config)
    device = resolve_device(config.device, _detect_devices())
    pipe = _pipeline_for(genai, model_dir, device)
    turn = BenchmarkConfig(**{**config.__dict__, "prompt": prompt})
    return str(_one_iteration(pipe, genai, turn).get("text") or "")


def _require_model_dir(config: BenchmarkConfig) -> Path:
    """The IR directory, from whichever way the caller named it.

    `--model-path` is the flag that exists and the one the suite's own help
    text already advertises for OpenVINO, so it is accepted first. Pointing it
    at the `.xml` is the obvious mistake and costs nothing to handle.
    """
    raw = config.extra.get("model_dir") or config.extra.get("model_path") or config.model
    if not raw:
        raise BackendError(
            "openvino_genai needs an exported model directory: pass "
            "--model-path pointing at a folder containing openvino_model.xml "
            "(for example an OpenVINO IR export from optimum-intel, or a "
            "pre-converted *-ov model from the OpenVINO organisation)."
        )
    model_dir = Path(str(raw))
    if model_dir.is_file() and model_dir.suffix == ".xml":
        model_dir = model_dir.parent
    if not (model_dir / _TOPOLOGY_FILE).is_file():
        raise BackendError(
            f"{model_dir} does not contain {_TOPOLOGY_FILE}; this is not an "
            "OpenVINO IR model directory"
        )
    return model_dir


def run(config: BenchmarkConfig, system: dict[str, Any]) -> dict[str, Any]:
    """Execute a measured OpenVINO GenAI benchmark and return a result."""
    info = detect()
    if info.status is not RuntimeStatus.AVAILABLE:
        raise BackendError(
            f"OpenVINO GenAI is not runnable here: {info.status.value} ({info.detail})"
        )

    genai = _import_openvino_genai()
    model_dir = _require_model_dir(config)
    visible = _detect_devices()
    device = resolve_device(config.device, visible)

    from ..metrics import aggregate_iteration_metrics, performance_per_watt
    from ..telemetry import TelemetrySampler
    from ..versions import CURRENT_SCHEMA_VERSION

    load_start = time.perf_counter()
    try:
        pipe = genai.LLMPipeline(str(model_dir), device)
    except Exception as exc:  # noqa: BLE001 - surface OpenVINO errors cleanly
        raise BackendError(f"failed to compile the model for {device}: {exc}") from exc
    load_time_ms = (time.perf_counter() - load_start) * 1000.0

    sampler = TelemetrySampler(interval_seconds=0.5)
    sampler.start()
    iterations: list[dict[str, Any]] = []
    try:
        for _ in range(config.warmup_runs):
            _one_iteration(pipe, genai, config)
        for _ in range(config.iterations):
            iterations.append(_one_iteration(pipe, genai, config))
    finally:
        sampler.stop()

    metrics = aggregate_iteration_metrics(iterations)
    telemetry = sampler.summary()
    metrics.update(telemetry)
    # Compiling the IR for a device is most of the wait before first use, and
    # it differs by an order of magnitude between CPU and GPU. It is a property
    # of the pipeline, so it is attached once rather than per iteration.
    metrics["load_time_ms"] = round(load_time_ms, 2)
    metrics["performance_per_watt"] = performance_per_watt(
        metrics.get("generation_tokens_per_second"), telemetry.get("average_power_watts")
    )

    names = device_names()
    telemetry_provenance = sampler.provenance()
    # Only for a run that used a GPU: on the CPU the zeroes are a correct
    # statement that this run did not touch one.
    if _project_device(device) == "gpu":
        metrics = disown_foreign_gpu_metrics(
            metrics,
            names.get(device),
            (telemetry_provenance.get("device") or {}).get("gpu_device_name"),
        )

    provenance = model_provenance(model_dir)
    weights = model_dir / _WEIGHTS_FILE

    return {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "run_id": new_run_id("openvino_genai"),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "system": system,
        "runtime": {
            "name": "openvino_genai",
            "version": info.version,
            "backend": f"openvino-genai-llm-pipeline:{device}",
            # The device that ran, in this project's vocabulary, plus the exact
            # OpenVINO name and the hardware behind it -- "GPU.1" is not
            # something a reader can interpret two years from now.
            "device": _project_device(device),
            "device_requested": config.device,
            "openvino_device": device,
            "openvino_device_name": names.get(device) or names.get(f"{device}.0") or None,
        },
        "model": {
            # `config.model` when the caller named it, because a directory name
            # is often a content hash -- a HuggingFace snapshot directory is
            # literally a commit id, and "339876973306da55..." tells a reader
            # of the published result nothing at all.
            "name": config.model or model_dir.name,
            "format": "openvino-ir",
            "parameters": None,
            "checksum": file_sha256(str(weights)) if weights.is_file() else None,
            "tokenizer": _tokenizer_identity(model_dir),
            **provenance,
        },
        "metrics": metrics,
        "telemetry": telemetry_provenance,
        "reproducibility": {
            "prompt": config.prompt,
            "max_tokens": config.max_tokens,
            "temperature": config.temperature,
            "seed": config.seed,
            "context_length": config.context_length,
            "warmup_runs": config.warmup_runs,
            "iterations": config.iterations,
            "command": (
                f"aihwbench benchmark --runtime openvino_genai "
                f"--model-dir {model_dir} --device {config.device}"
            ),
        },
        "iterations": iterations,
    }


def _normalise_device_name(name: str | None) -> str:
    """Enough of a device name to tell two cards apart.

    OpenVINO says "NVIDIA GeForce RTX 3080 Ti Laptop GPU (dGPU)" where
    nvidia-smi says "NVIDIA GeForce RTX 3080 Ti Laptop GPU", so an equality
    test calls one card two devices. That is not a cosmetic difference: the
    discrete GPU is the one case where the VRAM figure is real, so failing to
    match it there would throw away the only GPU memory measurement the
    project can actually take.

    The parenthesised parts go — OpenVINO's `(dGPU)`/`(iGPU)` class marker and
    the `(R)` in "Intel(R)" — and what is left is compared on its letters and
    digits alone.
    """
    stripped = re.sub(r"\([^)]*\)", " ", name or "")
    return "".join(ch for ch in stripped.lower() if ch.isalnum())


def disown_foreign_gpu_metrics(
    metrics: dict[str, Any], ran_on: str | None, sampled: str | None
) -> dict[str, Any]:
    """Drop GPU metrics that describe a different GPU than the run used.

    The telemetry sampler reads nvidia-smi, which reports the NVIDIA card
    whatever the run was actually on. For a run on an Intel iGPU that yields
    `peak_vram_mb: 0.0` and `avg_gpu_util_percent: 0.0` -- both true statements
    about an idle NVIDIA card, and both read as "this run used no graphics
    memory and no GPU". The iGPU's memory comes out of shared system RAM and
    is not measured here at all.

    Unmeasured is not zero, so the numbers go and the reason stays. A run on
    the CPU keeps them: there the zeroes are a correct statement about this
    run, namely that it did not touch the GPU.
    """
    if _normalise_device_name(ran_on) == _normalise_device_name(sampled):
        return metrics
    metrics["peak_vram_mb"] = None
    metrics["avg_gpu_util_percent"] = None
    source = metrics.setdefault("metric_source", {})
    if isinstance(source, dict):
        source["peak_vram_mb"] = "not_measured_for_this_device"
        source["avg_gpu_util_percent"] = "not_measured_for_this_device"
        source["gpu_telemetry_note"] = (
            f"the run used {ran_on or 'an unnamed device'} but telemetry samples "
            f"{sampled or 'no GPU'}; that device's memory and utilisation say "
            "nothing about this run, and an Intel iGPU allocates from shared "
            "system RAM where nvidia-smi cannot see it"
        )
    return metrics


def _project_device(openvino_device: str) -> str:
    """OpenVINO's device name in this project's vocabulary.

    `GPU.1` on this machine is a discrete NVIDIA card, so mapping every GPU.n
    to "gpu" would put an iGPU and a dGPU in the same comparison bucket. The
    exact name is kept alongside in `openvino_device`.
    """
    head = openvino_device.split(".")[0].lower()
    return {"cpu": "cpu", "gpu": "gpu", "npu": "npu"}.get(head, head)
