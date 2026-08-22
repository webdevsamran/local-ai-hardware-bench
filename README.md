# AIHWBench — Open Local AI Hardware Benchmark

**A vendor-neutral, reproducible framework for evaluating local AI runtimes across CPUs, GPUs, NPUs, AI PCs, workstations, mini PCs, and edge accelerators.**

> Originally created by **[@webdevsamran](https://github.com/webdevsamran)** (Original Creator / Founder / Lead Maintainer) and developed with contributions from the open-source community.

The framework already exists. Your hardware is the missing test platform.

## Who is this for?

| Audience | Start here |
| --- | --- |
| Personal user / AI PC owner | [Quick start](#quick-start) → `aihwbench doctor` |
| Developer choosing hardware | [Compatibility matrix](docs/compatibility-matrix.md) + published results |
| Contributor | [CONTRIBUTING.md](CONTRIBUTING.md) · [good first issues](https://github.com/webdevsamran/local-ai-hardware-bench/issues?q=label%3A%22good+first+issue%22) |
| Researcher | [Methodology](docs/methodology.md) · [CITATION.cff](CITATION.cff) |
| Runtime maintainer | [Plugin API](docs/guides/plugin-api.md) |
| Hardware vendor | [Vendor collaboration](docs/vendor-collaboration.md) · [Hardware needed](docs/hardware-needed.md) |
| Enterprise | [Enterprise overview](docs/enterprise/overview.md) (planned/future) |

## What this project does

`aihwbench` detects your hardware and installed AI runtimes, executes real
inference benchmarks locally, captures measured metrics (never estimates),
validates results against a versioned schema, and produces reproducible
reports.

## Why it exists

- **Reproducibility.** Most local-AI benchmark numbers online cannot be
  reproduced: unknown drivers, unknown quantization, unknown power state.
  Every result here records the full environment.
- **Compatibility.** A compatibility matrix that only contains genuinely
  tested combinations — one honest row beats twenty fabricated ones.
- **Performance per watt.** On laptops, mini PCs, and edge devices,
  efficiency matters as much as raw speed.
- **Engineering feedback.** Benchmarking exposes real bugs; we file them
  upstream with minimal reproductions.

## Hardware actually tested

Results are only claimed for machines where benchmarks genuinely ran.

| Platform | CPU | GPU | RAM | Status |
| --- | --- | --- | --- | --- |
| Acer Predator PT516-52s | Intel Core i9-12900H | NVIDIA RTX 3080 Ti Laptop (16 GB) | 32 GB | **Tested** |

See [docs/compatibility-matrix.md](docs/compatibility-matrix.md) for the
runtime × platform matrix, including what is *not* tested yet.

## Supported runtimes

"Tested" means a real benchmark executed on our reference machine and a
validated result file exists in [`results/published/`](results/published).

| Runtime | Detection | Benchmarking |
| --- | --- | --- |
| Ollama (CUDA) | Yes | **Yes — tested** |
| llama.cpp (`llama-server`, CUDA) | Yes | **Yes — tested** |
| ONNX Runtime (CPU + DirectML EPs) | Yes | **Yes — tested** |
| OpenVINO (CPU + GPU devices) | Yes | **Yes — tested** |
| NVIDIA CUDA | Yes | **Yes — tested** (via Ollama/llama.cpp CUDA builds) |
| NVIDIA TensorRT | Yes | Not yet (needs per-GPU engine builds) |
| AMD ROCm / Ryzen AI / Lemonade | Yes | Hardware needed (no AMD system available) |
| Qualcomm QNN | Yes | Hardware needed (no Snapdragon NPU available) |
| Hailo HailoRT | Yes | Hardware needed (no Hailo device available) |
| Windows ML / DirectML | Yes | **Yes — tested** (ONNX Runtime DML EP) |

Runtimes that cannot run on current hardware report an explicit
`HARDWARE_REQUIRED` status instead of pretending.

## Installation

Requires Python 3.10+.

```bash
git clone https://github.com/webdevsamran/local-ai-hardware-bench.git
cd local-ai-hardware-bench
pip install -e ".[dev]"
```

Optional but recommended for richer telemetry: `pip install psutil`.

## Quick start

```bash
# What hardware do I have? Any problems?
aihwbench doctor

# Which runtimes are usable right now?
aihwbench runtimes

# Full detection dump (JSON)
aihwbench detect

# Run a real benchmark (model must be pulled first)
ollama pull qwen2.5:0.5b-instruct-q4_K_M
aihwbench benchmark --runtime ollama --model qwen2.5:0.5b-instruct-q4_K_M

# Or run a versioned suite profile
aihwbench suite smoke --runtime ollama --model qwen2.5:0.5b-instruct-q4_K_M

# Validate and report on any result file
aihwbench validate results/raw/<run_id>.json
aihwbench report results/raw/<run_id>.json

# Compare two runs (refuses to compare incompatible workloads)
aihwbench compare results/raw/<a>.json results/raw/<b>.json

# Generate dataset views from published results
aihwbench export results/published --output results/dataset
```

### llama.cpp backend

```bash
aihwbench benchmark --runtime llama.cpp \
    --model-path path/to/model-q4_k_m.gguf \
    --device cuda
```

## Metrics captured

| Metric | Source | Notes |
| --- | --- | --- |
| Model load time | measured | where the runtime exposes it |
| Time to first token (TTFT) | measured | first streamed token |
| Prompt processing tok/s | measured | runtime-reported counts/durations |
| Generation tok/s | measured | runtime-reported counts/durations |
| Latency mean/p50/p90/p95/p99, stddev | measured | across iterations |
| Peak RAM / VRAM | sampled | background telemetry thread |
| CPU/GPU utilization | sampled | `psutil` / `nvidia-smi` |
| Temperature, power draw | sampled | `nvidia-smi`; null elsewhere |
| Performance per watt | derived | gen tok/s ÷ average watts |

**Metrics that cannot be measured reliably are reported as `null` and shown
as "not measured" in reports. They are never estimated.**

## Result format & schema

Every result is a JSON document validated against schema 1.0:

- Formal JSON Schema: [`schemas/result_schema.schema.json`](schemas/result_schema.schema.json)
- Semantic validator: [`benchmark/schemas.py`](benchmark/schemas.py)
- Full field reference: [`schemas/README.md`](schemas/README.md)

Validation covers types, ISO-8601 UTC timestamps, run-id format,
non-negative metrics, utilisation ranges (0–100), and reproducibility
typing.

## Comparison safety

Comparisons are classified explicitly:

- **STRICTLY_COMPARABLE** — model checksum/format/quantization, prompt,
  token budget, sampling settings, seed, context length, batch/concurrency,
  warmups/iterations, runtime/backend/device all match.
- **CONDITIONALLY_COMPARABLE** — workload matches but caveats exist
  (power profile, OS version, runtime version).
- **NOT_COMPARABLE** — direct metric comparison would be misleading;
  the CLI refuses to emit deltas unless you pass `--force`, and returns
  machine-readable reasons.

See [docs/methodology.md](docs/methodology.md).

## Result trust states

Published results carry one of three trust states (see
[submission pipeline](docs/results/submission-pipeline.md)):

| State | Meaning |
| --- | --- |
| `VERIFIED` | Executed/reproduced by the project on real hardware |
| `COMMUNITY_VALIDATED` | Submitted, validated, reviewed; not independently reproduced |
| `UNVERIFIED` | Reference only |

## Automation & CI

Exit codes are a stable contract (`benchmark/exit_codes.py`):

| Code | Meaning |
| --- | --- |
| 0 | success |
| 1 | validation/data error |
| 2 | usage/backend error |
| 3 | results NOT_COMPARABLE |
| 4 | configuration error |
| 5 | performance regression detected (regression gate) |

## Reproducing a published result

Each committed result in [`results/published/`](results/published) includes a
`reproducibility` block: exact prompt, sampling parameters, context length,
warm-up/iteration policy, model checksum, runtime version, driver versions,
power profile, and the exact command to re-run it.

## Contributing

We welcome code, backends, hardware results, documentation, and reviews.
Start with [CONTRIBUTING.md](CONTRIBUTING.md). Good first issues are
labeled in the issue tracker. See also:

- [Backend plugin API](docs/guides/plugin-api.md)
- [Result submission pipeline](docs/results/submission-pipeline.md)
- [Governance](GOVERNANCE.md) · [Code of Conduct](CODE_OF_CONDUCT.md)

## Documentation

| Audience | Start here |
| --- | --- |
| New user | [Quickstart](docs/getting-started/quickstart.md) · [Installation](docs/getting-started/installation.md) · [FAQ](FAQ.md) |
| Contributor | [Onboarding](docs/contributing/onboarding.md) · [Troubleshooting](TROUBLESHOOTING.md) · [Glossary](GLOSSARY.md) |
| Runtime maintainer | [Backends overview](docs/backends/overview.md) · [Plugin API](docs/guides/plugin-api.md) |
| Researcher | [Reproducibility](docs/research/reproducibility.md) · [Citation](docs/research/citation.md) |
| Security/compliance | [Privacy](docs/security/privacy.md) · [Supply chain](docs/security/supply-chain.md) |
| Hardware | [Hardware overview](docs/hardware/overview.md) |

## Vendor collaboration

Hardware vendors (AMD, Intel, NVIDIA, Qualcomm, Hailo, mini-PC OEMs, ...):
we welcome evaluation units, engineering samples, dev kits, loaner systems,
and remote hardware access. In return you receive independent runtime
validation, reproducible data, installation docs, bug reports, and upstream
PRs. We do not promise favorable results — see
[docs/vendor-collaboration.md](docs/vendor-collaboration.md) and
[docs/hardware-needed.md](docs/hardware-needed.md).

## Ecosystem (planned)

| Offering | Status |
| --- | --- |
| AIHWBench Community (this repo) | Available — Apache-2.0 |
| AIHWBench Dataset | Public validated dataset built from published results |
| AIHWBench Enterprise / Cloud / Certified / Labs | Planned — see [TRADEMARKS.md](TRADEMARKS.md); nothing exists yet |

## Security & privacy

Detection output is sanitized: no serial numbers, MAC addresses, usernames,
home paths, or network identifiers are collected. Published artifacts pass
a fail-closed privacy scan. See [SECURITY.md](SECURITY.md).

## License & attribution

Apache-2.0 — see [LICENSE](LICENSE) and [NOTICE](NOTICE).
Created by [@webdevsamran](https://github.com/webdevsamran); see
[AUTHORS.md](AUTHORS.md) and [CONTRIBUTORS.md](CONTRIBUTORS.md).
To cite this work use [CITATION.cff](CITATION.cff).