# Benchmark Report - onnxruntime-1787391388

- **Timestamp:** 2026-08-22T09:36:28Z
- **Schema:** 1.0
- **Git commit:** `6cec992520ccbbb92defb40e6677604483e4ca80`

## System

- **OS:** Windows 11 (10.0.26200)
- **Platform:** Predator PT516-52s
- **CPU:** 12th Gen Intel(R) Core(TM) i9-12900H (14C/20T)
- **GPU:** NVIDIA GeForce RTX 3080 Ti Laptop GPU (16,384 MB VRAM)
- **NPU:** none detected
- **RAM:** 31.70 GB

## Runtime & Model

- **Runtime:** onnxruntime 1.29.0
- **Backend:** execution-providers:CPUExecutionProvider on cpu
- **Model:** mobilenetv2-12.onnx (format: onnx, quantization: not measured)

## Metrics

| Metric | Value |
| --- | --- |
| Model load time | 55.21 ms |
| Time to first token | not measured |
| Prompt processing (tok/s) | not measured |
| Generation (tok/s) | not measured |
| Total latency (mean) | 3.33 ms |
| Latency p50 | 2.52 ms |
| Latency p95 | 5.63 ms |
| Peak RAM | 20,702.59 MB |
| Peak VRAM | 1,315.00 MB |
| CPU utilization (avg) | 0.00% |
| GPU utilization (avg) | 38.00% |
| Max temperature | 64.00 C |
| Average power | 22.27 W |
| Performance per watt (tok/s/W) | 13.47 |

## Reproducibility

```text
aihwbench benchmark --runtime onnxruntime --model-path E:\models\mobilenetv2-12.onnx --device cpu
```

- Prompt: None
- Max tokens: None, temperature: None, seed: None
- Context length: None, warm-up runs: 2, measured iterations: 5

> Metrics reported as 'not measured' could not be captured reliably on this platform; they are never estimated.