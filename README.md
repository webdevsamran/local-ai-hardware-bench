# Open Local AI Hardware Benchmark

**A vendor-neutral, reproducible framework for evaluating local AI runtimes across CPUs, GPUs, NPUs, AI PCs, workstations, mini PCs, and edge accelerators.**

> The framework already exists. Your hardware is the missing test platform.

## What this project does

`aihwbench` detects your hardware and installed AI runtimes, executes real
inference benchmarks locally, captures measured metrics (never estimates),
validates results against a versioned schema, and produces reproducible
human-readable reports.

The long-term goal is a public, engineering-grade evidence base of how local
AI runtimes actually perform on real hardware — useful for developers choosing
hardware, for runtime maintainers fixing performance bugs, and for hardware
vendors who want independent validation.

## Why it exists

- **Reproducibility.** Most local-AI benchmark numbers online cannot be
  reproduced: unknown drivers, unknown quantization, unknown power state.
  Every result here records the full environment.
- **Compatibility.** A compatibility matrix that only contains genuinely
  tested combinations — one honest row beats twenty fabricated ones.
- **Performance per watt.** On laptops, mini PCs, and edge devices,
  efficiency matters as much as raw speed.
- **Engineering feedback.** Benchmarking exposes real bugs; we file them
  upstream (llama.cpp, Ollama, ONNX Runtime, OpenVINO, ROCm, ...) with
  minimal reproductions.

## Hardware actually tested

Results are only claimed for machines where benchmarks genuinely ran.

| Platform | CPU | GPU | RAM | Status |
| --- | --- | --- | --- | --- |
| Acer Predator PT516-52s | Intel Core i9-12900H | NVIDIA RTX 3080 Ti Laptop (16 GB) | 32 GB | **Tested** |

See [docs/compatibility-matrix.md](docs/compatibility-matrix.md) for the
runtime × platform matrix, including what is *not* tested yet.

## Supported runtimes

| Runtime | Detection | Benchmarking |
| --- | --- | --- |
| Ollama | Yes | **Yes (tested)** |
| llama.cpp (`llama-server`) | Yes | Yes (implemented) |
| ONNX Runtime | Yes | Planned (v0.3) |
| OpenVINO / GenAI | Yes | Planned (v0.4) |
| AMD ROCm / Ryzen AI / Lemonade | Yes | Planned (v0.5) |
| NVIDIA CUDA / TensorRT | Yes | Planned (v0.6) |
| Qualcomm QNN | Yes | Planned (v0.7) |
| Hailo HailoRT | Yes | Planned (v0.8) |
| Windows ML / DirectML | Yes | Planned |

Unsupported runtimes report an explicit status
(`NOT_INSTALLED`, `HARDWARE_REQUIRED`, `CONFIGURATION_REQUIRED`,
`UNSUPPORTED_PLATFORM`) instead of pretending.

## Installation

Requires Python 3.10+.

```bash
git clone https://github.com/webdevsamran/local-ai-hardware-bench.git
cd local-ai-hardware-bench
pip install -e ".[dev]"
```

Optional but recommended for richer telemetry:

```bash
pip install psutil
```

## Quick start

```bash
# What hardware do I have?
aihwbench system-info

# Which runtimes are usable right now?
aihwbench runtimes

# Full detection dump (JSON)
aihwbench detect

# Run a real benchmark (model must be pulled first)
ollama pull qwen2.5:0.5b-instruct-q4_K_M
aihwbench benchmark --runtime ollama --model qwen2.5:0.5b-instruct-q4_K_M

# Validate and report on any result file
aihwbench validate results/raw/<run_id>.json
aihwbench report results/raw/<run_id>.json

# Compare two runs (warns when not comparable)
aihwbench compare results/raw/<a>.json results/raw/<b>.json
```

### llama.cpp backend

```bash
aihwbench benchmark --runtime llama.cpp \
    --model-path path/to/model-q4_k_m.gguf \
    --device cuda
```

The backend starts `llama-server`, waits for health, then measures streamed
completions. Token counts come from the server's usage object.

## Metrics captured

| Metric | Source | Notes |
| --- | --- | --- |
| Model load time | measured | where the runtime exposes it |
| Time to first token (TTFT) | measured | first streamed token |
| Prompt processing tok/s | measured | runtime-reported counts/durations |
| Generation tok/s | measured | runtime-reported counts/durations |
| Total latency, p50, p95 | measured | across iterations |
| Peak RAM / VRAM | sampled | background telemetry thread |
| CPU/GPU utilization | sampled | `psutil` / `nvidia-smi` |
| Temperature, power draw | sampled | `nvidia-smi`; null elsewhere |
| Performance per watt | derived | gen tok/s ÷ average watts |

**Metrics that cannot be measured reliably are reported as `null` and shown
as "not measured" in reports. They are never estimated.**

## Result format

Every result is a JSON document validated against schema 1.0
(see [`benchmark/schemas.py`](benchmark/schemas.py)):

```json
{
  "schema_version": "1.0",
  "run_id": "ollama-1755850000",
  "timestamp": "2026-08-22T09:00:00Z",
  "git_commit": "<sha>",
  "system": { "os": "...", "cpu": "...", "gpu": "...", "npu": null, "ram_gb": 31.7 },
  "runtime": { "name": "ollama", "version": "...", "backend": "ollama-http-api" },
  "model":   { "name": "...", "format": "gguf", "quantization": null, "checksum": "..." },
  "metrics": { "ttft_ms": 45.2, "generation_tokens_per_second": 61.3, "...": null },
  "reproducibility": {
    "prompt": "...", "max_tokens": 128, "temperature": 0.0, "seed": 42,
    "context_length": 2048, "warmup_runs": 2, "iterations": 5,
    "command": "aihwbench benchmark --runtime ollama --model ..."
  }
}
```

## Reproducing a published result

Each committed result in [`results/published/`](results/published) includes a
`reproducibility` block: exact prompt, sampling parameters, context length,
warm-up/iteration policy, model checksum, runtime version, driver versions,
power profile, and the exact command to re-run it. Follow that block on
equivalent hardware to reproduce the measurement.

## Benchmark fairness

Comparisons are only published between materially identical workloads:
same model revision and quantization, same context length, same prompt,
same generated-token budget, same sampling parameters (temperature 0,
fixed seed), documented warm-up and iteration counts, and recorded power
mode. The compare command warns loudly when two results differ in any of
these dimensions. See [docs/methodology.md](docs/methodology.md).

## Model tiers

Models are never committed to Git. Tiers keep comparisons apples-to-apples
([configs/models.json](configs/models.json)):

| Tier | Size | Example |
| --- | --- | --- |
| Smoke | ~0.5B | qwen2.5:0.5b-instruct-q4_K_M |
| Standard | 1B–4B | llama3.2:3b-instruct-q4_K_M |
| Performance | 7B–14B | qwen2.5:7b-instruct-q4_K_M |
| High-memory | 32B+ | qwen2.5:32b-instruct-q4_K_M |

## Adding a runtime backend

1. Create `benchmark/backends/<name>.py` exposing `detect()` and `run()`.
2. Register it in `benchmark/backends/__init__.py`.
3. Add tests: detection must never crash, and `run()` must raise
   `BackendError` cleanly when prerequisites are missing.
4. Update the compatibility matrix only after a real run.

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Adding a hardware platform

Run the framework on your machine, commit the sanitized result plus a
platform note under `platforms/<vendor>/`, and open a PR. See
[docs/methodology.md](docs/methodology.md).

## Vendor collaboration

Hardware vendors (AMD, Intel, NVIDIA, Qualcomm, Hailo, Seeed Studio,
MINISFORUM, GEEKOM, Beelink, GMKtec, ASUS, Lenovo, Khadas, ...): we welcome
evaluation units, engineering samples, dev kits, loaner systems, and remote
hardware access. In return you receive independent runtime validation,
reproducible data, installation docs, bug reports, and upstream PRs.
We do not promise favorable results — see
[docs/vendor-collaboration.md](docs/vendor-collaboration.md) and
[docs/hardware-needed.md](docs/hardware-needed.md).

## Security & privacy

Detection output is sanitized: no serial numbers, MAC addresses, usernames,
home paths, or network identifiers are collected. See [SECURITY.md](SECURITY.md).

## License

Apache-2.0. See [LICENSE](LICENSE).