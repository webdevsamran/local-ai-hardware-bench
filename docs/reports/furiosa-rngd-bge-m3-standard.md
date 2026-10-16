# Benchmark Report - furiosa-rngd-bge-m3-standard

- **Timestamp:** 2026-10-16T15:13:30Z
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
- **Model:** furiosa-ai/bge-m3 (format: fxb, quantization: FP32)
- **Checksum:** `sha256:3b85151963188861e2c8f56022743b680fd6345f01718abeaa0caa1e09c51d62`

## Metrics

| Metric | Value |
| --- | --- |
| Model load time | 3,074.67 ms |
| Time to first token | not measured |
| Prompt processing (tok/s) | 53,696.91 |
| Generation (tok/s) | not measured |
| Total latency (mean) | 76.97 ms |
| Latency p50 | 76.28 ms |
| Latency p95 | 83.98 ms |
| Peak RAM | 3,850.00 MB |
| Peak VRAM | 48,308.00 MB |
| CPU utilization (avg) | 5.20% |
| GPU utilization (avg) | not measured |
| Max temperature | 49.53 C |
| Average power | 109.00 W |
| Performance per watt | 3.85 inf/s/W |

## Reproducibility

```text
python3 /workspace/run_phase2_all_models_and_metrics.py --model furiosa-ai/bge-m3
```

- Prompt: 'Batch=32 x SeqLen=128 pooling encode'
- Max tokens: None, temperature: None, seed: 42
- Context length: 8192, warm-up runs: 2, measured iterations: 5

> Metrics reported as 'not measured' could not be captured reliably on this platform; they are never estimated.