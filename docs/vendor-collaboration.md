# Vendor Collaboration

## What vendors can provide

- Evaluation units and engineering samples
- Development kits (Jetson, Hailo, Snapdragon, Ryzen AI, Core Ultra)
- Loaner systems for a defined benchmark window
- Pre-production systems under NDA (results published only with approval)
- Remote hardware access (SSH/IP-KVM) where shipping hardware is impractical

## What the project delivers in return

- **Independent runtime validation** on your hardware, with the full
  environment recorded
- **Reproducible benchmark data** — every number ships with its reproduction
  command, model checksum, driver versions, and power profile
- **Installation documentation** — working setup notes for your platform,
  including the workarounds we had to find
- **Bug reports** — minimal reproductions filed against runtimes
  (llama.cpp, Ollama, ONNX Runtime, OpenVINO, ROCm, Lemonade, ...), not
  against your support queue alone
- **Upstream contributions** — focused fixes and tests where feasible
- **Optimization feedback** — concrete observations (e.g., thermal
  throttling onset, driver overhead, memory-bandwidth limits)

## Editorial independence

We do not promise favorable benchmark results, and we do not accept review
approval over published data. If a vendor disagrees with a finding, we will
publish their technical response alongside it. Hardware providers are
credited in result files (`reproducibility.hardware_provider`) unless they
prefer anonymity.

## Practical arrangements

1. Open an issue titled `Hardware: <platform>` describing the unit.
2. We confirm the runtime coverage it unlocks and agree on a return window.
3. On receipt: detection dump, smoke-tier validation, then standard-tier
   benchmarks per [methodology.md](methodology.md).
4. Results are validated, published to `results/published/`, and the
   compatibility matrix is updated within days of a successful run.

## Current status

The framework is functional and one real GPU system has been benchmarked
(see `results/published/`). Coverage gaps that vendor hardware would close
are listed in [hardware-needed.md](hardware-needed.md).