# Benchmark Report - furiosa-rngd-qwen3-reranker-4b-standard

- **Timestamp:** 2026-10-16T15:13:51Z
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
- **Model:** furiosa-ai/Qwen3-Reranker-4B (format: fxb, quantization: BF16)
- **Checksum:** `sha256:b706bb25d87a7a2bda63b345465a6a84146d450ac28b5e29f21ad18434bc5e49`

## Metrics

| Metric | Value |
| --- | --- |
| Model load time | 2,621.56 ms |
| Time to first token | not measured |
| Prompt processing (tok/s) | 9,890.61 |
| Generation (tok/s) | not measured |
| Total latency (mean) | 404.57 ms |
| Latency p50 | 414.13 ms |
| Latency p95 | 424.37 ms |
| Peak RAM | 3,850.00 MB |
| Peak VRAM | 47,664.00 MB |
| CPU utilization (avg) | 5.20% |
| GPU utilization (avg) | not measured |
| Max temperature | 52.74 C |
| Average power | 114.12 W |
| Performance per watt | 0.68 inf/s/W |

## Reproducibility

```text
python3 /workspace/run_phase2_all_models_and_metrics.py --model furiosa-ai/Qwen3-Reranker-4B
```

- Prompt: 'Batch=32 x SeqLen=128 pooling encode'
- Max tokens: None, temperature: None, seed: 42
- Context length: 8192, warm-up runs: 2, measured iterations: 5

> Metrics reported as 'not measured' could not be captured reliably on this platform; they are never estimated.