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
| `tensorrt` | TensorRT | Linux/Win | HARDWARE_REQUIRED until validated |
| `rocm` | ROCm | Linux | HARDWARE_REQUIRED until validated |
| `qnn` | Qualcomm QNN | Windows ARM64 | HARDWARE_REQUIRED until validated |
| `hailo` | HailoRT | Linux | HARDWARE_REQUIRED until validated |
| `windows_ml` | Windows ML | Windows 11 | CONFIGURATION_REQUIRED |

## Third-party plugins

Backends can be distributed as separate packages registering the
`aihwbench.backends` entry point. See the
[Plugin API guide](../guides/plugin-api.md) for the contract
(`BACKEND_API_VERSION = 1`).

## Honesty policy

A backend never fabricates metrics. If a runtime does not expose TTFT,
power or temperature, those fields are `null`. "Tested" hardware claims
require real execution on that hardware.