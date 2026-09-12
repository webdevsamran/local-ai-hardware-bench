# Hardware Coverage Gaps

This is not a wishlist. Each target below names the runtime it unlocks, the
engineering question it answers, and the concrete deliverables it produces.
The project benchmarks what it can access; these are the gaps that currently
limit coverage.

**The backends are written.** Every runtime named below has a working
implementation in this repository — ROCm, Lemonade, QNN, TensorRT, HailoRT,
Windows ML, MLX, ExLlamaV2, Vulkan, SYCL, WebGPU, plus Intel NPU counters. What
is missing is not code, it is silicon. Each one detects its runtime, refuses
rather than falling back to a CPU under an accelerator's name, and produces a
result through the same measurement path every published number here came from.

That changes what access is worth. Somebody with one of these machines does not
need to write an integration first: clone, `pip install -e ".[dev]"`,
`aihwbench doctor` to see what the machine reports, then `aihwbench benchmark
--runtime <name>`. If it works, the result is publishable. If it does not, the
failure is a bug report with a stack trace, which is nearly as useful.

The honest caveat: none of these paths has run on the hardware it targets. They
are written against each vendor's documented API and unit-tested with the
vendor calls faked. First contact will find things — that is what first contact
is for, and it is a much smaller job than starting from nothing.

## Priority targets

### AMD Ryzen AI / Ryzen AI Max (NPU + Radeon)
- **Required runtime:** Lemonade / Ryzen AI VitisAI EP, ONNX Runtime, ROCm (Radeon)
- **Benchmark purpose:** NPU vs iGPU vs dGPU LLM throughput on the same SoC;
  performance-per-watt on battery vs plugged.
- **Engineering gap:** No AMD NPU/Radeon system is currently accessible. ROCm
  cells in the matrix are blocked on Linux-capable Radeon hardware.
- **Already written:** `lemonade` backend (OpenAI-compatible API over Ryzen
  AI), `rocm` backend (llama.cpp HIP build for GGUF, ONNX Runtime ROCm
  provider for ONNX).
- **Needs the hardware:** NPU telemetry (AMD PSM has no counter wired),
  published standard-tier results, upstream issues for any driver or runtime
  incompatibility found.

### Intel Core Ultra (Meteor Lake/Lunar Lake NPU + Arc)
- **Required runtime:** OpenVINO / OpenVINO GenAI, ONNX Runtime, Windows ML
- **Benchmark purpose:** Intel NPU LLM latency/throughput; OpenVINO GenAI
  vs ONNX Runtime DirectML on identical silicon.
- **Engineering gap:** No Core Ultra machine available; the current Intel
  CPU (12th gen) has no NPU.
- **Already written:** `openvino` and `openvino_genai` backends (the latter
  measured on Intel CPU and iGPU here), `windows_ml` via DirectML, and NPU
  utilization counters read from the Windows NPU Engine counter set and the
  `intel_vpu` sysfs on Linux — sampled during a run rather than after it,
  because a reading taken afterwards describes an idle device.
- **Needs the hardware:** NPU *power* (no counter exposes it), and the
  measurement that matters most here — NPU against iGPU against CPU on one
  chip, which the OpenVINO backend can already run three ways.

### Qualcomm Snapdragon X (ARM64 Windows)
- **Required runtime:** QNN / ONNX Runtime QNN EP
- **Benchmark purpose:** Hexagon NPU performance and battery-life impact on
  ARM64 Windows; x64-emulation penalty measurement.
- **Engineering gap:** No Snapdragon X device; QNN SDK requires NPU hardware
  for context-binary execution.
- **Already written:** `qnn` backend via ONNX Runtime's QNN execution
  provider, including a node-assignment check that refuses when the provider
  loads but is handed none of the graph — the failure a float32 model produces
  on an NPU that wants quantized QDQ operators.
- **Needs the hardware:** ARM64 CI job, Snapdragon
  platform note.

### NVIDIA RTX / RTX PRO desktop + Jetson Orin / Thor
- **Required runtime:** TensorRT / TensorRT-LLM, CUDA, llama.cpp CUDA
- **Benchmark purpose:** TensorRT-LLM vs llama.cpp CUDA on identical GPUs;
  Jetson power-constrained inference (performance per watt at 15–60 W).
- **Engineering gap:** Current RTX 3080 Ti Laptop covers CUDA via Ollama/
  llama.cpp, but TensorRT engine builds and Jetson-class edge power
  envelopes are untested.
- **Already written:** `tensorrt` backend via ONNX Runtime's TensorRT
  provider (the engine build lands in `load_time_ms`, where it belongs), and
  `jetson` via llama.cpp.
- **Needs the hardware:** Jetson platform note,
  edge power-envelope benchmark suite.

### Hailo-8 / 8L / 10H
- **Required runtime:** HailoRT + compiled HEF models
- **Benchmark purpose:** Edge accelerator throughput/latency for vision and
  LLM-class workloads; PCIe vs M.2 vs USB attach overhead.
- **Engineering gap:** No Hailo device or HailoRT installation.
- **Already written:** `hailo` backend over HailoRT's `InferVStreams`,
  reporting inferences per second rather than tokens and recording which
  device architecture the HEF was compiled for.
- **Needs the hardware:** HEF benchmark configs,
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