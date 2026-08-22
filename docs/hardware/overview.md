# Hardware Overview

AIHWBench detects and benchmarks across hardware classes. Detection is
conservative: unknown capabilities are reported as absent rather than guessed.

## Supported hardware classes

| Class | Detection | Telemetry | Benchmark status |
|---|---|---|---|
| x86 CPU (Intel/AMD) | Full | CPU util via psutil | Tested (reference machine) |
| NVIDIA GPU (CUDA) | Full (name, VRAM, driver) | nvidia-smi where available | Runtime-dependent |
| Intel GPU (OpenVINO) | Via OpenVINO device query | Limited | Tested (iGPU) |
| AMD GPU (ROCm) | Placeholder | None | HARDWARE_REQUIRED |
| Intel NPU / AMD XDNA / Hexagon | Placeholder | None | HARDWARE_REQUIRED |
| Hailo accelerators | Placeholder | None | HARDWARE_REQUIRED |

## Telemetry availability

Telemetry sources are recorded per result (`telemetry.source`). Metrics a
platform cannot measure are `null` — never interpolated.

- RAM/VRAM peaks: sampled during the run
- CPU/GPU utilization: platform-specific
- Power/temperature: only where an OS/driver API exposes it

## Reference platforms

See [platforms/](../../platforms/) for the machines used to produce
published results.

## Adding your hardware

1. Run `aihwbench doctor` and `aihwbench detect`
2. Run a benchmark with an available runtime
3. Submit the sanitized result — see
   [submission pipeline](../results/submission-pipeline.md)