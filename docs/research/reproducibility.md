# Reproducibility Guide

## What makes a result reproducible

Every result document records the complete experimental context:

| Dimension | Fields |
|---|---|
| Framework | schema_version, protocol_version, git_commit, run_id, timestamp |
| Hardware | CPU topology, GPU+VRAM, NPU, RAM, drivers, OS/kernel/arch |
| Software | runtime name/version/backend/device/provider |
| Model | name, revision, format, quantization, sha256 checksum, tokenizer |
| Workload | prompt id/text, context length, token budget, sampling params, seed |
| Protocol | warmups, iterations, batch size, concurrency, power profile |

## Re-running a published experiment

1. Match the recorded runtime version (or note deviations honestly)
2. Use the same model file (verify the checksum)
3. Run the same suite profile (`configs/suites/*.json`)
4. Compare with `aihwbench compare --force` if identities differ slightly

## Comparison safety

The classifier refuses authoritative comparisons when model identity,
workload, or protocol differ. See [methodology](../methodology.md).

## Known variance sources

- Thermal state and power profile of the machine
- Background load
- Runtime autotuning (e.g. first-run kernel selection)
- Driver updates between runs