# Benchmark Report - furiosa-rngd-deepseek-r1-distill-llama-8b-fp8-standard

- **Timestamp:** 2026-10-16T15:03:17Z
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
- **Model:** RedHatAI/DeepSeek-R1-Distill-Llama-8B-FP8-dynamic (format: fxb, quantization: FP8-Dynamic)
- **Checksum:** `sha256:a72ebb9e59365291261b4db205013b823eec9f122841ce855cdfb7de4c717146`

## Metrics

| Metric | Value |
| --- | --- |
| Model load time | 88,730.47 ms |
| Time to first token | 62.59 ms |
| Prompt processing (tok/s) | 16,360.53 |
| Generation (tok/s) | 109.83 |
| Total latency (mean) | 2,384.35 ms |
| Latency p50 | 2,384.46 ms |
| Latency p95 | 2,384.54 ms |
| Peak RAM | 4,320.00 MB |
| Peak VRAM | 47,258.85 MB |
| CPU utilization (avg) | 6.50% |
| GPU utilization (avg) | not measured |
| Max temperature | 50.00 C |
| Average power | 141.26 W |
| Performance per watt | 0.78 tok/s/W |

## Reproducibility

```text
python3 /workspace/run_benchmark.py --model RedHatAI/DeepSeek-R1-Distill-Llama-8B-FP8-dynamic --slug furiosa-rngd-deepseek-r1-distill-llama-8b-fp8-standard
```

- Prompt: 'Synthetic uncached token sequence (ISL=1024, OSL=256)'
- Max tokens: 256, temperature: 0.0, seed: 42
- Context length: 8192, warm-up runs: 2, measured iterations: 5

> Metrics reported as 'not measured' could not be captured reliably on this platform; they are never estimated.