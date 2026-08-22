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
| ROCm | Hardware Needed (no AMD GPU; Windows HIP SDK only) | — |
| QNN | Hardware Needed (no Snapdragon NPU) | — |
| TensorRT | Not tested (needs per-GPU engine builds; CUDA toolkit absent) | — |
| HailoRT | Hardware Needed (no Hailo device) | — |

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

## Rules for updating this matrix

1. A cell may move to **Tested** only when a result file exists in
   `results/published/` produced by a real benchmark on that platform.
2. Detection status alone never upgrades a cell to Tested.
3. Cross-vendor cells (e.g., ROCm on NVIDIA) are marked `n/a`, not failed.