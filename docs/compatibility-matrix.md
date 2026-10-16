# Compatibility Matrix

Statuses:

- **Tested** — a real benchmark executed on this exact platform; evidence in `results/published/`.
- **Supported** — backend implemented and expected to work; not yet executed here.
- **Experimental** — implemented but unvalidated.
- **Planned** — on the roadmap.
- **Hardware Needed** — requires hardware the project does not currently have.
- **Unknown** — not yet evaluated.

Every "Tested" cell links to a committed result file with a reproducibility block.

## Current machine (Acer Predator PT516-52s)

| Runtime | Status | Evidence |
| --- | --- | --- |
| Ollama (CUDA, RTX 3080 Ti) | **Tested** | `results/published/ollama-1787388930.json` |
| llama.cpp `llama-server` (CUDA) | **Tested** | `results/published/llamacpp-1787391945.json` |
| ONNX Runtime (CPU EP) | **Tested** | `results/published/onnxruntime-1787391388.json` |
| ONNX Runtime (DirectML EP) | **Tested** | `results/published/onnxruntime-1787391455.json` |
| OpenVINO (CPU device) | **Tested** | `results/published/openvino-1787391625.json` |
| OpenVINO (GPU device) | **Tested** | `results/published/openvino-1787391710.json` |
| ROCm | Implemented; hardware needed (no AMD GPU; Windows HIP SDK only) | — |
| QNN | Implemented; hardware needed (no Snapdragon NPU) | — |
| TensorRT | Implemented; TensorRT execution provider absent here | — |
| HailoRT | Implemented; hardware needed (no Hailo device) | — |

## Platform × runtime matrix

| Platform | llama.cpp | Ollama | ONNX | OpenVINO | ROCm | QNN | TensorRT | HailoRT |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **This machine** (i9-12900H + RTX 3080 Ti Laptop) | **Tested** | **Tested** | **Tested** (CPU+DML) | **Tested** (CPU+GPU) | Hardware Needed | Hardware Needed | Not tested | Hardware Needed |
| AMD Ryzen AI / AI Max | Hardware Needed | Hardware Needed | Hardware Needed | Hardware Needed | Hardware Needed | n/a | n/a | n/a |
| Intel Core Ultra (NPU) | Hardware Needed | Hardware Needed | Hardware Needed | Hardware Needed | n/a | n/a | n/a | n/a |
| Snapdragon X (ARM64) | Hardware Needed | Hardware Needed | Hardware Needed | n/a | n/a | Hardware Needed | n/a | n/a |
| NVIDIA RTX / RTX PRO desktop | Hardware Needed | Hardware Needed | Hardware Needed | n/a | n/a | n/a | Hardware Needed | n/a |
| NVIDIA Jetson Orin/Thor | Hardware Needed | Hardware Needed | Hardware Needed | n/a | n/a | n/a | Hardware Needed | n/a |
| Hailo-8 / 8L / 10H | n/a | n/a | Hardware Needed | n/a | n/a | n/a | n/a | Hardware Needed |
| Generic x86-64 CPU | Supported | Supported | Planned | Planned | n/a | n/a | n/a | n/a |
| ARM SBC (Seeed/Khadas class) | Hardware Needed | Hardware Needed | Hardware Needed | n/a | n/a | n/a | n/a | Hardware Needed |
| RISC-V | Unknown | Unknown | Unknown | n/a | n/a | n/a | n/a | n/a |

## Every registered runtime

The matrix above covers the runtimes with published results. This table covers
*all* of them, so a backend cannot be added to the registry without appearing
here — `tests/test_backends.py` fails if one is missing. That guard exists
because the omission is silent otherwise: a runtime that works but is
undocumented is one nobody knows to try.

| Runtime | Backend kind | Status here | Why |
| --- | --- | --- | --- |
| `ollama` | HTTP API | **Tested** | Published results |
| `llama.cpp` | Managed `llama-server` | **Tested** | Published results |
| `onnxruntime` | In-process | **Tested** | Published results (CPU + DirectML) |
| `openvino` | In-process | **Tested** | Published results (CPU + GPU) |
| `openvino_genai` | In-process | Supported | LLM pipeline; not yet run here |
| `lmstudio` | OpenAI-compatible HTTP | Experimental | Needs the LM Studio server running |
| `vllm` | OpenAI-compatible HTTP | Supported | Linux + NVIDIA/ROCm only; not runnable on this machine |
| `sglang` | OpenAI-compatible HTTP | Supported | Linux + NVIDIA/ROCm only; not runnable on this machine |
| `lemonade` | OpenAI-compatible HTTP | Supported | Implemented over its `/api/v1` surface; needs Lemonade Server on Ryzen AI to execute |
| `rocm` | llama.cpp HIP / ONNX Runtime EP | Supported | Implemented, dispatching on the artifact; no AMD GPU here to execute it |
| `mlx` | In-process (`mlx_lm`) | Supported | Implemented, recording unified-memory peak from MLX itself; Apple Silicon needed to execute |
| `qnn` | ONNX Runtime EP | Supported | Implemented, refusing when the provider is assigned no graph nodes; no Snapdragon NPU here |
| `tensorrt` | ONNX Runtime EP | Supported | Implemented; the engine is built on the benchmarking machine and its cost lands in `load_time_ms`. TensorRT provider absent here |
| `hailo` | In-process (HailoRT) | Supported | Implemented over `InferVStreams`; reports inferences/sec, not tokens. Needs a device and a compiled `.hef` |
| `windows_ml` | ONNX Runtime (DirectML) | **Tested** | 101 of 104 MobileNetV2 nodes ran on the GPU here |
| `vulkan` | llama.cpp build variant | Experimental | Two Vulkan devices found here (Iris Xe, RTX 3080 Ti); this llama.cpp build is CUDA-only, so the limit is the build and not the hardware |
| `sycl` | llama.cpp build variant | Experimental | Intel Iris Xe present; oneAPI absent, so nothing can reach it |
| `webgpu` | llama.cpp Dawn / browser | Supported (native) | The native Dawn path is implemented and fully measurable. The in-browser path stays unimplemented: the sandbox exposes no power, VRAM or temperature, and those nulls would read to the classifier as agreeing with a native result's |
| `exllamav2` | In-process (CUDA) | Supported | Implemented over the dynamic generator; needs PyTorch+CUDA, `exllamav2` and EXL2 weights. Its fractional bits-per-weight do not map onto GGUF quantization labels |
| `jetson` | llama.cpp on L4T | Hardware Needed | aarch64 + Tegra; unified memory, and the `nvpmodel` power mode must be recorded or results are not comparable |
| `arm_sbc` | llama.cpp CPU | Hardware Needed | Raspberry Pi and similar, identified by device-tree model; throttling and power-delivery flags recorded because both present as "slow board" |

"Detection only" means the backend reports honestly whether the runtime is
present and refuses to benchmark, rather than pretending. `aihwbench doctor
--json` prints this table's live equivalent for any machine.

## Rules for updating this matrix

1. A cell may move to **Tested** only when a result file exists in
   `results/published/` produced by a real benchmark on that platform.
2. Detection status alone never upgrades a cell to Tested.
3. Cross-vendor cells (e.g., ROCm on NVIDIA) are marked `n/a`, not failed.