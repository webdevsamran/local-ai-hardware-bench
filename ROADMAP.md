# Roadmap

Milestones are adjusted to actual hardware availability. A milestone ships
when its deliverables are genuinely tested — not before.

## v0.1 — Framework + first real backend (current)
- [x] Cross-platform hardware detection (CPU, GPU, RAM, NPU, drivers)
- [x] Runtime detection with explicit status states
- [x] Ollama backend: real streamed benchmarking on CUDA
- [x] llama.cpp backend implementation (`llama-server`)
- [x] Result schema 1.0 + validation
- [x] Telemetry sampling (RAM/VRAM/util/temp/power via nvidia-smi/psutil)
- [x] Reports, comparison, CLI (`aihwbench`)
- [x] Test suite + CI
- [ ] First published result set (in progress)

## v0.2 — Standardized llama.cpp/Ollama benchmarking
- llama.cpp timing-log parsing (recover generation tok/s)
- Model load-time measurement for Ollama (server log parsing)
- Sustained-load profile (longer iterations, thermal tracking)
- Published standard-tier results across available runtimes

## v0.3 — ONNX Runtime
- ONNX model pipeline (LLM + vision workloads)
- CPU / DirectML / CUDA EP comparison on current machine

## v0.4 — Intel / OpenVINO
- OpenVINO GenAI backend
- NPU telemetry hooks (needs Core Ultra hardware)

## v0.5 — AMD / ROCm / Ryzen AI / Lemonade
- ROCm backend (Linux)
- Lemonade / Ryzen AI backend (needs Ryzen AI hardware)

## v0.6 — NVIDIA CUDA / TensorRT
- TensorRT backend with per-GPU engine build pipeline
- TensorRT-LLM where practical

## v0.7 — Qualcomm QNN
- QNN backend + ARM64 Windows CI runner (needs Snapdragon X)

## v0.8 — Hailo
- HailoRT backend, HEF benchmark configs (needs Hailo device)

## v0.9 — Community result submission
- Result submission workflow (PR template + automated validation in CI)
- Public leaderboard generated from validated results only

## v1.0 — Stable multi-platform methodology
- Schema frozen at 2.0 with backward-compatible reader
- Methodology review with external maintainers
- At least three genuinely tested hardware classes