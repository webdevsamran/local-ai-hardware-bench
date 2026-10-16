# Benchmark Report - furiosa-rngd-llama31-8b-fp8-sustained

- **Timestamp:** 2026-10-16T14:42:33Z
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
- **Model:** furiosa-ai/Meta-Llama-3.1-8B-Instruct-FP8-dynamic (format: fxb, quantization: FP8-Dynamic)
- **Checksum:** `sha256:05abbb7f5d8b4fd420d892dfaaddd67979c12634d9251e36c8b9146917ee097b`

## Metrics

| Metric | Value |
| --- | --- |
| Model load time | 106,904.58 ms |
| Time to first token | 63.46 ms |
| Prompt processing (tok/s) | 16,137.06 |
| Generation (tok/s) | 109.62 |
| Total latency (mean) | 9,392.62 ms |
| Latency p50 | 9,395.08 ms |
| Latency p95 | 9,395.67 ms |
| Peak RAM | 4,320.00 MB |
| Peak VRAM | 47,406.85 MB |
| CPU utilization (avg) | 6.50% |
| GPU utilization (avg) | not measured |
| Max temperature | 52.98 C |
| Average power | 142.07 W |
| Performance per watt | 0.77 tok/s/W |

## Reproducibility

```text
python3 /workspace/run_benchmark.py --model furiosa-ai/Meta-Llama-3.1-8B-Instruct-FP8-dynamic --slug furiosa-rngd-llama31-8b-fp8-sustained
```

- Prompt: 'Synthetic uncached token sequence (ISL=1024, OSL=1024)'
- Max tokens: 1024, temperature: 0.0, seed: 42
- Context length: 8192, warm-up runs: 2, measured iterations: 5

> Metrics reported as 'not measured' could not be captured reliably on this platform; they are never estimated.