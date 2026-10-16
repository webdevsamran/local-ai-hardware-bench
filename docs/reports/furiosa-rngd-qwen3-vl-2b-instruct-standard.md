# Benchmark Report - furiosa-rngd-qwen3-vl-2b-instruct-standard

- **Timestamp:** 2026-10-16T15:08:59Z
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
- **Model:** furiosa-ai/Qwen3-VL-2B-Instruct (format: fxb, quantization: BF16)
- **Checksum:** `sha256:a30f8d74f7e8ce087d3c9a04a1af3caa6f8a5d194dd2ebf1caf394f63f626c06`

## Metrics

| Metric | Value |
| --- | --- |
| Model load time | 68,532.00 ms |
| Time to first token | 37.18 ms |
| Prompt processing (tok/s) | 27,541.44 |
| Generation (tok/s) | 186.52 |
| Total latency (mean) | 1,401.58 ms |
| Latency p50 | 1,404.33 ms |
| Latency p95 | 1,404.98 ms |
| Peak RAM | 4,320.00 MB |
| Peak VRAM | 44,686.47 MB |
| CPU utilization (avg) | 6.50% |
| GPU utilization (avg) | not measured |
| Max temperature | 47.30 C |
| Average power | 230.00 W |
| Performance per watt | 0.81 tok/s/W |

## Reproducibility

```text
python3 /workspace/run_benchmark.py --model furiosa-ai/Qwen3-VL-2B-Instruct --slug furiosa-rngd-qwen3-vl-2b-instruct-standard
```

- Prompt: 'Synthetic uncached token sequence (ISL=1024, OSL=256)'
- Max tokens: 256, temperature: 0.0, seed: 42
- Context length: 8192, warm-up runs: 2, measured iterations: 5

> Metrics reported as 'not measured' could not be captured reliably on this platform; they are never estimated.