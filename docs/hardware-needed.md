# Hardware Coverage Gaps

This is not a wishlist. Each target below names the runtime it unlocks, the
engineering question it answers, and the concrete deliverables it produces.
The project benchmarks what it can access; these are the gaps that currently
limit coverage.

## Priority targets

### AMD Ryzen AI / Ryzen AI Max (NPU + Radeon)
- **Required runtime:** Lemonade / Ryzen AI VitisAI EP, ONNX Runtime, ROCm (Radeon)
- **Benchmark purpose:** NPU vs iGPU vs dGPU LLM throughput on the same SoC;
  performance-per-watt on battery vs plugged.
- **Engineering gap:** No AMD NPU/Radeon system is currently accessible. ROCm
  cells in the matrix are blocked on Linux-capable Radeon hardware.
- **Planned deliverables:** Ryzen AI + Lemonade backend, NPU telemetry
  (AMD PSM), published standard-tier results, upstream issues for any
  driver/runtime incompatibilities found.

### Intel Core Ultra (Meteor Lake/Lunar Lake NPU + Arc)
- **Required runtime:** OpenVINO / OpenVINO GenAI, ONNX Runtime, Windows ML
- **Benchmark purpose:** Intel NPU LLM latency/throughput; OpenVINO GenAI
  vs ONNX Runtime DirectML on identical silicon.
- **Engineering gap:** No Core Ultra machine available; the current Intel
  CPU (12th gen) has no NPU.
- **Planned deliverables:** OpenVINO backend (v0.4), NPU power telemetry,
  Core Ultra platform note.

### Qualcomm Snapdragon X (ARM64 Windows)
- **Required runtime:** QNN / ONNX Runtime QNN EP
- **Benchmark purpose:** Hexagon NPU performance and battery-life impact on
  ARM64 Windows; x64-emulation penalty measurement.
- **Engineering gap:** No Snapdragon X device; QNN SDK requires NPU hardware
  for context-binary execution.
- **Planned deliverables:** QNN backend (v0.7), ARM64 CI job, Snapdragon
  platform note.

### NVIDIA RTX / RTX PRO desktop + Jetson Orin / Thor
- **Required runtime:** TensorRT / TensorRT-LLM, CUDA, llama.cpp CUDA
- **Benchmark purpose:** TensorRT-LLM vs llama.cpp CUDA on identical GPUs;
  Jetson power-constrained inference (performance per watt at 15–60 W).
- **Engineering gap:** Current RTX 3080 Ti Laptop covers CUDA via Ollama/
  llama.cpp, but TensorRT engine builds and Jetson-class edge power
  envelopes are untested.
- **Planned deliverables:** TensorRT backend (v0.6), Jetson platform note,
  edge power-envelope benchmark suite.

### Hailo-8 / 8L / 10H
- **Required runtime:** HailoRT + compiled HEF models
- **Benchmark purpose:** Edge accelerator throughput/latency for vision and
  LLM-class workloads; PCIe vs M.2 vs USB attach overhead.
- **Engineering gap:** No Hailo device or HailoRT installation.
- **Planned deliverables:** HailoRT backend (v0.8), HEF benchmark configs,
  edge accelerator comparison report.

### Mini PC / AI PC vendors (MINISFORUM, GEEKOM, Beelink, GMKtec, ASUS NUC, Lenovo, Khadas, Seeed reComputer)
- **Required runtime:** varies by SoC (Ryzen AI, Core Ultra, Snapdragon,
  Jetson, Hailo)
- **Benchmark purpose:** Sustained thermal performance in constrained
  chassis — where laptops and mini PCs diverge most from desktops.
- **Engineering gap:** No loaner/eval units; sustained-load thermal data is
  the single most requested and least published metric in this segment.
- **Planned deliverables:** Sustained-load benchmark profile, per-platform
  thermal notes, compatibility matrix rows.

## What we provide in return

See [vendor-collaboration.md](vendor-collaboration.md). In short: independent
validation, reproducible data, real bug reports, upstream fixes, and honest
documentation — never guaranteed favorable results.