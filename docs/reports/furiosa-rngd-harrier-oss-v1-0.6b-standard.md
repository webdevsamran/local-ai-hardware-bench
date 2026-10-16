# Benchmark Report - furiosa-rngd-harrier-oss-v1-0.6b-standard

- **Timestamp:** 2026-10-16T15:13:22Z
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
- **Backend:** furiosa-llm-pooling on npu1 (FuriosaAI RNGD TP=8)
- **Model:** furiosa-ai/harrier-oss-v1-0.6b (format: fxb, quantization: BF16)
- **Checksum:** `sha256:4d38eb6a5660a45aefe0f7437f0961dfad80769627592a0c39819347e698dc61`

## Metrics

| Metric | Value |
| --- | --- |
| Model load time | 1,790.27 ms |
| Time to first token | not measured |
| Prompt processing (tok/s) | 39,365.69 |
| Generation (tok/s) | not measured |
| Total latency (mean) | 105.84 ms |
| Latency p50 | 104.05 ms |
| Latency p95 | 116.55 ms |
| Peak RAM | 3,850.00 MB |
| Peak VRAM | 48,052.00 MB |
| CPU utilization (avg) | 5.20% |
| GPU utilization (avg) | not measured |
| Max temperature | 50.09 C |
| Average power | 46.25 W |
| Performance per watt | 6.65 inf/s/W |

## Reproducibility

```text
python3 /workspace/run_phase2_all_models_and_metrics.py --model furiosa-ai/harrier-oss-v1-0.6b
```

- Prompt: 'Batch=32 x SeqLen=128 pooling encode'
- Max tokens: None, temperature: None, seed: 42
- Context length: 8192, warm-up runs: 2, measured iterations: 5

> Metrics reported as 'not measured' could not be captured reliably on this platform; they are never estimated.