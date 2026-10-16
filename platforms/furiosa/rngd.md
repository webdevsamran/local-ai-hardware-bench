# Platform: FuriosaAI RNGD (48GB HBM3 PCIe Accelerator)

**Status: Tested** — full multi-modality hardware benchmark suite executed and verified under Schema 2.1.

## Hardware Specifications

| Component | Verified Value |
| --- | --- |
| Accelerator | 1x FuriosaAI RNGD PCIe Card (`npu1`) |
| Architecture | 2nd-Gen NPU / Tensor Contraction Processor (TCP) |
| Processing Elements | 8x PE Cores (`pe:0` through `pe:7`, Ring Cluster Topology `TP=8, PP=1`) |
| Core / TCP Clocks | 2000 MHz Core Clock / 1000 MHz TCP Clock |
| On-Card Memory | 48 GB HBM3 (`51,002,736,640` bytes / `48,640 MiB` physical capacity) |
| TDP / Idle Power | 300 W TDP ceiling / `40.0 W` measured idle board power |
| Firmware / PERT | Firmware `2026.4.0, 93d67f3` / PERT `2026.4.0 (rev: 235f8db81)` |
| Host CPU | Dual-Socket AMD EPYC 9354 32-Core Processor (64C / 128T) |
| Host OS | Ubuntu 24.04.4 LTS (Linux Kernel 6.8.0-106-generic) |

## Software Stack at Time of Testing

- **Inference Engine**: `furiosa-llm 2026.4.0-release (rev: b1baffa)` (vLLM-compatible Python & OpenAI HTTP server)
- **Compiler Revision**: `fc43f6a779-c03e584974` (Furiosa Executable Bundle `.fxb` format)
- **System Management / Telemetry**: `furiosa-smi 2026.4.0` (`info --format json` and `status --format json`)
- **Python**: `3.12.3`
- **Structured Output Backends**: XGrammar & LLGuidance hardware-assisted constrained decoding

## Architecture & Telemetry Notes

1. **Tensor Contraction Processor (TCP) & Tensor Parallelism (`TP=8`)**:
   A single RNGD card exposes 8 PE cores (`npu:1:0` through `npu:1:7`) connected via an on-die ring topology (`RingTopology { kind: Cluster }`). All flagship models compiled for a single RNGD card execute with `tensor_parallel_size=8, pipeline_parallel_size=1` (`TP=8, PP=1`).
2. **PagedAttention HBM3 KV-Cache Allocation**:
   During model initialization, `furiosa-llm` reserves static weight buffers and target I/O staging buffers in HBM3, dedicating the remaining HBM3 budget (`37.4 GiB` to `41.5 GiB` on 4B–8B FP8 models, or `24.2 GiB` on 20.9B MXFP4 MoE) to PagedAttention KV-cache blocks (`block_size=2048` for standard global attention, supporting up to `131,072` context length on `Meta-Llama-3.1-8B-Instruct-FP8-dynamic` and `gpt-oss-20b`).
3. **Dual-Command `furiosa-smi` Telemetry**:
   - `furiosa-smi info --format json` reports board power (`power`, in Watts), die temperature (`temperature`, in °C), `core_clock` (MHz), `tcp_clock` (MHz), and governor profile.
   - `furiosa-smi status --format json` reports per-core PE utilization (`pe_utilizations` across `pe_core: 0..7`) and exact HBM3 byte allocation (`memory.used_size` / `memory.total_size`).
4. **Compiler Version Pinning (`.fxb`)**:
   Furiosa Executable Bundles (`.fxb`) are strictly version-locked to the compiler revision (`2026.4.0`). Attempting to load an older `2025.3.0` FXB artifact (such as `furiosa-ai/Qwen2.5-0.5B-Instruct`) fails cleanly at load time with a compiler version mismatch error, whereas models sharing identical tensor graph topologies and shapes (such as `RedHatAI/DeepSeek-R1-Distill-Llama-8B-FP8-dynamic` paired with the `Meta-Llama-3.1-8B-Instruct-FP8-dynamic` 2026.4.0 FXB bundle) execute at full native hardware speed (`110 tok/s` single-stream, `1,520+ tok/s` batched).
