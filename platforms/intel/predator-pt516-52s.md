# Platform: Acer Predator PT516-52s

**Status: Tested** — first benchmarked platform of this project.

## Hardware

| Component | Value |
| --- | --- |
| CPU | Intel Core i9-12900H (14C/20T, Alder Lake-H) |
| dGPU | NVIDIA GeForce RTX 3080 Ti Laptop, 16 GB GDDR6 |
| iGPU | Intel Iris Xe Graphics |
| NPU | None (12th gen predates Intel AI Boost) |
| RAM | 32 GB DDR5 |
| OS | Windows 11 Pro, Build 26200 |

## Drivers / software at time of testing

- NVIDIA driver 610.74 (CUDA UMD 13.3)
- Ollama 0.32.15

## Notes & quirks

- WDDM mode: GPU memory reporting via `nvidia-smi` is reliable; WMI
  `Win32_VideoController.AdapterRAM` truncates to ~4 GB (known WMI
  limitation) — the framework therefore uses `nvidia-smi` when present.
- Laptop power profile matters: results record the active Windows power
  scheme. For comparable numbers, use plugged-in + high-performance.
- Hybrid graphics: inference runs on the dGPU; the iGPU drives the display.