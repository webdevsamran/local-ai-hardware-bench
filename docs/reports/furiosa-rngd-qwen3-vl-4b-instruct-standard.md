# Benchmark Report - furiosa-rngd-qwen3-vl-4b-instruct-standard

- **Timestamp:** 2026-10-16T15:13:00Z
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
- **Model:** furiosa-ai/Qwen3-VL-4B-Instruct (format: fxb, quantization: BF16)
- **Checksum:** `sha256:3799b3503832a8868e2fc0d9a6e9abc680edab9ef6463b851a097d1fe4e4e95d`

## Metrics

| Metric | Value |
| --- | --- |
| Model load time | 101,531.57 ms |
| Time to first token | 66.24 ms |
| Prompt processing (tok/s) | 15,458.68 |
| Generation (tok/s) | 103.73 |
| Total latency (mean) | 2,529.29 ms |
| Latency p50 | 2,524.46 ms |
| Latency p95 | 2,537.54 ms |
| Peak RAM | 4,320.00 MB |
| Peak VRAM | 44,646.49 MB |
| CPU utilization (avg) | 6.50% |
| GPU utilization (avg) | not measured |
| Max temperature | 50.19 C |
| Average power | 134.96 W |
| Performance per watt | 0.77 tok/s/W |

## Reproducibility

```text
python3 /workspace/run_benchmark.py --model furiosa-ai/Qwen3-VL-4B-Instruct --slug furiosa-rngd-qwen3-vl-4b-instruct-standard
```

- Prompt: 'Synthetic uncached token sequence (ISL=1024, OSL=256)'
- Max tokens: 256, temperature: 0.0, seed: 42
- Context length: 8192, warm-up runs: 2, measured iterations: 5

> Metrics reported as 'not measured' could not be captured reliably on this platform; they are never estimated.