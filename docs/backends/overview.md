# Backends Overview

A *backend* connects AIHWBench to a runtime (Ollama, llama.cpp, ONNX
Runtime, OpenVINO, ...). Each backend:

- detects the runtime and reports an honest status
  (AVAILABLE / NOT_INSTALLED / HARDWARE_REQUIRED / CONFIGURATION_REQUIRED);
- executes benchmark iterations against real models;
- records only metrics the runtime actually exposes (null otherwise).

## Built-in backends

| Backend | Runtime | Platforms | Notes |
|---|---|---|---|
| `ollama` | Ollama HTTP API | Win/Linux/macOS | Token counts from API responses |
| `llama.cpp` | llama-server | Win/Linux/macOS | Requires llama-server binary |
| `onnxruntime` | ONNX Runtime | Win/Linux/macOS | DirectML/CUDA/CPU providers |
| `openvino` | OpenVINO | Win/Linux | CPU + Intel GPU devices |
| `openvino_genai` | OpenVINO GenAI | Win/Linux | Measured LLM pipeline; CPU/GPU/NPU, one device per run |
| `tensorrt` | TensorRT (ONNX Runtime EP) | Linux/Win | Engine built on the benchmarking machine; written, not yet run on an NVIDIA box |
| `rocm` | ROCm | Linux | GGUF via llama.cpp HIP, ONNX via the ROCm EP; written, needs a Radeon |
| `qnn` | Qualcomm QNN (ONNX Runtime EP) | Windows ARM64 | Refuses when the NPU is handed no graph nodes; written, needs a Snapdragon X |
| `hailo` | HailoRT | Linux | Pre-compiled `.hef` only; inferences/sec, not tokens; written, needs a Hailo device |
| `windows_ml` | Windows ML (DirectML) | Windows 11 | **Measured here**: 101/104 MobileNetV2 nodes on the GPU |
| `lemonade` | AMD Lemonade (Ryzen AI) | Win/Linux | OpenAI-compatible API; written, needs Ryzen AI |
| `exllamav2` | ExLlamaV2 | Linux/Win | EXL2 weights, fractional bits per weight; written, needs an NVIDIA GPU |
| `mlx` | Apple MLX | macOS | Unified memory recorded from MLX itself; written, needs Apple Silicon |
| `vulkan` / `sycl` / `webgpu` | llama.cpp build variants | varies | Device discovered from `--list-devices`, never assumed |

## Third-party plugins

Backends can be distributed as separate packages registering the
`aihwbench.backends` entry point. See the
[Plugin API guide](../guides/plugin-api.md) for the contract
(`BACKEND_API_VERSION = 1`).

## Honesty policy

A backend never fabricates metrics. If a runtime does not expose TTFT,
power or temperature, those fields are `null`. "Tested" hardware claims
require real execution on that hardware.