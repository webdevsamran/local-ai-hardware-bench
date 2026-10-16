# Benchmark Report - furiosa-rngd-qwen3-4b-fp8-sustained

- **Timestamp:** 2026-10-16T14:35:51Z
- **Schema:** 2.1
- **Git commit:** `bd689f2`

## System

- **OS:** Linux (Ubuntu 24.04 LTS) (6.8.0-147-generic)
- **Platform:** FuriosaAI RNGD PCIe Server
- **CPU:** AMD EPYC 9354 32-Core Processor (64C/128T)
- **GPU:** FuriosaAI RNGD (48GB HBM3 NPU) (48,640 MB VRAM)
- **NPU:** FuriosaAI RNGD (npu1, 8x PE TCP Cores, 48GB HBM3)
- **RAM:** 1,007.40 GB

## Runtime & Model

- **Runtime:** furiosa-llm 2026.4.0-release (rev: b1baffa)
- **Backend:** furiosa-llm-engine on npu1 (FuriosaAI RNGD TP=8)
- **Model:** furiosa-ai/Qwen3-4B-FP8 (format: fxb, quantization: FP8)
- **Checksum:** `sha256:dad93fb2e17104146b30a08c3c34d8fd122c9d893ecfb8a4a50db27a7b0827c7`

## Metrics

| Metric | Value |
| --- | --- |
| Model load time | 4,804.38 ms |
| Time to first token | 61.63 ms |
| Prompt processing (tok/s) | 16,614.71 |
| Generation (tok/s) | 142.31 |
| Total latency (mean) | 7,253.25 ms |
| Latency p50 | 7,249.91 ms |
| Latency p95 | 7,260.21 ms |
| Peak RAM | 4,320.00 MB |
| Peak VRAM | 47,693.73 MB |
| CPU utilization (avg) | 6.50% |
| GPU utilization (avg) | not measured |
| Max temperature | 51.86 C |
| Average power | 121.29 W |
| Performance per watt | 1.17 tok/s/W |

## Reproducibility

```text
python3 /workspace/run_benchmark.py --model furiosa-ai/Qwen3-4B-FP8 --slug furiosa-rngd-qwen3-4b-fp8-sustained
```

- Prompt: 'Synthetic uncached token sequence (ISL=1024, OSL=1024)'
- Max tokens: 1024, temperature: 0.0, seed: 42
- Context length: 8192, warm-up runs: 2, measured iterations: 5

> Metrics reported as 'not measured' could not be captured reliably on this platform; they are never estimated.