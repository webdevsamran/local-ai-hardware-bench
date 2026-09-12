# Credits and acknowledgements

AIHWBench measures other people's software. Almost everything interesting it
reports is a property of a runtime somebody else wrote, running a model
somebody else trained, on silicon somebody else designed. This file credits
them, and everyone who has contributed here.

If you are missing from this file, that is a bug — please
[open an issue](https://github.com/webdevsamran/local-ai-hardware-bench/issues).

## People

### Original creator

- **[@webdevsamran](https://github.com/webdevsamran)** — Original Creator ·
  Founder · Lead Maintainer. Designed and built the benchmark harness, the
  comparison-safety classifier, the result schema and the dashboard.

### Contributors

Listed in [CONTRIBUTORS.md](CONTRIBUTORS.md), with the git history as the
authoritative record. Every contributor retains copyright over their
contributions; no copyright assignment is required.

### Hardware providers

None yet. When a machine is lent, donated or made remotely accessible, the
provider is credited here **and** recorded alongside every result that machine
produced, because a reader evaluating a number deserves to know where the
hardware came from. The terms are in
[docs/vendor-collaboration.md](docs/vendor-collaboration.md), and the current
gaps are in [docs/hardware-needed.md](docs/hardware-needed.md).

### Reviewers

The methodology in this repository
[has not yet been externally reviewed](docs/methodology.md). When it is, the
reviewers are credited here whether or not the review was comfortable reading.

## Runtimes this project benchmarks

Each of these is the reason a corresponding backend exists. Benchmarking a
project is not an endorsement by it, and none of the projects below has
reviewed or approved anything published here.

| Project | What it provides | Licence |
| --- | --- | --- |
| [llama.cpp](https://github.com/ggml-org/llama.cpp) | GGUF inference, `llama-server`, the CUDA/Vulkan/SYCL/HIP/Metal build variants, and `llama-bench` — the reference point for raw local throughput | MIT |
| [Ollama](https://github.com/ollama/ollama) | Model management and a local serving API; the first backend this project measured | MIT |
| [ONNX Runtime](https://github.com/microsoft/onnxruntime) | Cross-platform graph execution and the execution-provider model that the DirectML, QNN, TensorRT and ROCm paths all route through | MIT |
| [OpenVINO](https://github.com/openvinotoolkit/openvino) and [OpenVINO GenAI](https://github.com/openvinotoolkit/openvino.genai) | Intel CPU, iGPU, dGPU and NPU inference; the only runtime here that ran the same model on three devices of one machine | Apache-2.0 |
| [vLLM](https://github.com/vllm-project/vllm) | High-throughput serving, PagedAttention, and the OpenAI-compatible protocol several backends speak | Apache-2.0 |
| [SGLang](https://github.com/sgl-project/sglang) | Structured generation and high-throughput serving | Apache-2.0 |
| [MLX](https://github.com/ml-explore/mlx) | Apple Silicon inference against unified memory | MIT |
| [ExLlamaV2](https://github.com/turboderp-org/exllamav2) | EXL2 quantized inference on consumer NVIDIA GPUs | MIT |
| [TensorRT](https://developer.nvidia.com/tensorrt) / [TensorRT-LLM](https://github.com/NVIDIA/TensorRT-LLM) | NVIDIA engine compilation and optimised inference | Apache-2.0 |
| [LM Studio](https://lmstudio.ai/) | A local OpenAI-compatible server many users already have running | Proprietary (free) |
| [AMD Lemonade / Ryzen AI](https://github.com/lemonade-sdk/lemonade) | Ryzen AI NPU serving over an OpenAI-compatible API | Apache-2.0 |
| [Qualcomm QNN](https://www.qualcomm.com/developer/software/neural-processing-sdk-for-ai) | Hexagon NPU execution on Snapdragon | Proprietary SDK |
| [Hailo HailoRT](https://github.com/hailo-ai/hailort) | Edge accelerator runtime | MIT / LGPL components |
| [DirectML](https://github.com/microsoft/DirectML) / Windows ML | Vendor-neutral GPU acceleration on Windows; the path by which this project verified accelerator node placement end to end | MIT |

## Models

Every model benchmarked here is recorded in
[docs/models/zoo.md](docs/models/zoo.md) with its licence, its SHA-256 checksum
and the exact command that obtains it — because a benchmark that cannot name
what it ran is not reproducible. Credit for the models themselves belongs to
their authors; the zoo carries the attribution and licence terms for each.

The published results were produced with **Qwen2.5 0.5B Instruct** (Apache-2.0,
read from the file's own GGUF header) and **MobileNetV2 opset 12**
(Apache-2.0 per the ONNX Model Zoo's terms — declared by a maintainer, not read
from the artifact, because the ONNX format carries no licence field).

## Prior art in benchmarking

This project disagrees with some of these about scope, and owes all of them
something:

- **[MLCommons](https://mlcommons.org/) / MLPerf** — the reference for what
  auditable, rules-based benchmarking looks like. MLPerf Client is the closest
  competitor in intent; the disagreement is about who gets to be measured, not
  about rigour.
- **[LocalScore](https://localscore.ai/)** — demonstrated that a crowdsourced
  local-inference dataset can exist at all. The disagreement is about composite
  scores and provenance, not about the idea.
- **Bench360** ([arXiv:2511.16682](https://arxiv.org/abs/2511.16682)) — the
  academic work closest to this one, and the paper that states plainly that it
  defines no criteria for when results are comparable. That sentence is a
  direct reason the comparison-safety classifier here exists.
- **`llama-bench`** — the default answer for raw local speed, and the honest
  baseline every serving-path measurement in this project is checked against.

## Software this project is built with

**Python side.** The core has **zero required runtime dependencies** on
purpose: a benchmark that drags in a dependency tree measures the dependency
tree. Optional and development tooling:
[pytest](https://pytest.org), [Ruff](https://docs.astral.sh/ruff/),
[mypy](https://mypy-lang.org/), [psutil](https://github.com/giampaolo/psutil),
[NumPy](https://numpy.org/), [jsonschema](https://github.com/python-jsonschema/jsonschema),
[PyArrow](https://arrow.apache.org/) (Parquet export only).

**Dashboard.** [React](https://react.dev/),
[React Router](https://reactrouter.com/), [Vite](https://vite.dev/),
[TypeScript](https://www.typescriptlang.org/),
[Vitest](https://vitest.dev/), [Testing Library](https://testing-library.com/),
[ESLint](https://eslint.org/), [jsdom](https://github.com/jsdom/jsdom) and
[axe-core](https://github.com/dequelabs/axe-core), which the accessibility gate
runs over every prerendered page. The charts are hand-written SVG with no chart
library, so there is nothing to credit there and nothing to load at runtime.

**Infrastructure.** [GitHub Actions](https://github.com/features/actions) for
CI, GitHub Pages for the dashboard, [Shields.io](https://shields.io/) for the
badges, and [Sigstore cosign](https://github.com/sigstore/cosign) for the
optional signing path.

## Licence

This file is part of AIHWBench, licensed under Apache-2.0. Trademarks and
product names belong to their respective owners; see
[TRADEMARKS.md](TRADEMARKS.md). Mentioning a product here is attribution, not a
claim of affiliation, sponsorship or endorsement in either direction.
