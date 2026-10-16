# Benchmark Report - furiosa-rngd-qwen3-8b-fp8-sustained

- **Timestamp:** 2026-10-16T14:49:41Z
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
- **Model:** furiosa-ai/Qwen3-8B-FP8 (format: fxb, quantization: FP8)
- **Checksum:** `sha256:636952146e2a222822fee7c62d758e2abe7efc26f63f8e32d49f11df6a9d28b8`

## Metrics

| Metric | Value |
| --- | --- |
| Model load time | 113,076.20 ms |
| Time to first token | 75.76 ms |
| Prompt processing (tok/s) | 13,516.50 |
| Generation (tok/s) | 103.46 |
| Total latency (mean) | 9,961.19 ms |
| Latency p50 | 9,963.48 ms |
| Latency p95 | 9,965.82 ms |
| Peak RAM | 4,320.00 MB |
| Peak VRAM | 47,841.73 MB |
| CPU utilization (avg) | 6.50% |
| GPU utilization (avg) | not measured |
| Max temperature | 53.16 C |
| Average power | 139.99 W |
| Performance per watt | 0.74 tok/s/W |

## Reproducibility

```text
python3 /workspace/run_benchmark.py --model furiosa-ai/Qwen3-8B-FP8 --slug furiosa-rngd-qwen3-8b-fp8-sustained
```

- Prompt: 'Synthetic uncached token sequence (ISL=1024, OSL=1024)'
- Max tokens: 1024, temperature: 0.0, seed: 42
- Context length: 8192, warm-up runs: 2, measured iterations: 5

> Metrics reported as 'not measured' could not be captured reliably on this platform; they are never estimated.