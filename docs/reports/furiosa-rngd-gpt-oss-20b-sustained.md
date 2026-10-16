# Benchmark Report - furiosa-rngd-gpt-oss-20b-sustained

- **Timestamp:** 2026-10-16T14:56:55Z
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
- **Model:** furiosa-ai/gpt-oss-20b (format: fxb, quantization: MXFP4)
- **Checksum:** `sha256:b20c983dc9da5b2a5cea01d0d3ec1136fe912822cd2256b7e42eb4eda6c082f4`

## Metrics

| Metric | Value |
| --- | --- |
| Model load time | 161,431.74 ms |
| Time to first token | 118.93 ms |
| Prompt processing (tok/s) | 8,610.05 |
| Generation (tok/s) | 135.73 |
| Total latency (mean) | 7,654.08 ms |
| Latency p50 | 7,655.82 ms |
| Latency p95 | 7,670.51 ms |
| Peak RAM | 4,320.00 MB |
| Peak VRAM | 40,848.69 MB |
| CPU utilization (avg) | 6.50% |
| GPU utilization (avg) | not measured |
| Max temperature | 53.11 C |
| Average power | 121.24 W |
| Performance per watt | 1.12 tok/s/W |

## Reproducibility

```text
python3 /workspace/run_benchmark.py --model furiosa-ai/gpt-oss-20b --slug furiosa-rngd-gpt-oss-20b-sustained
```

- Prompt: 'Synthetic uncached token sequence (ISL=1024, OSL=1024)'
- Max tokens: 1024, temperature: 0.0, seed: 42
- Context length: 8192, warm-up runs: 2, measured iterations: 5

> Metrics reported as 'not measured' could not be captured reliably on this platform; they are never estimated.