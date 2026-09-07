# AIHWBench Leaderboard

Generated from 6 validated result(s) in `results/published`.

| Run | Runtime | Model | GPU | Gen tok/s | TTFT ms | Perf/W | Perf/W unit |
| --- | --- | --- | --- | --- | --- | --- | --- |
| llamacpp-1787391945 | llama.cpp | qwen2.5-0.5b-instruct-q4_k_m.gguf | NVIDIA GeForce RTX 3080 Ti Laptop GPU | 360.87 | 14.52 | 13.485 | tok/s/W |
| ollama-1787388930 | ollama | qwen2.5:0.5b-instruct-q4_K_M | NVIDIA GeForce RTX 3080 Ti Laptop GPU | 110.93 | 2,069.71 | 4.24 | tok/s/W |
| onnxruntime-1787391388 | onnxruntime | mobilenetv2-12.onnx | NVIDIA GeForce RTX 3080 Ti Laptop GPU | not measured | not measured | 13.468 | inf/s/W |
| onnxruntime-1787391455 | onnxruntime | mobilenetv2-12.onnx | NVIDIA GeForce RTX 3080 Ti Laptop GPU | not measured | not measured | 11.354 | inf/s/W |
| openvino-1787391625 | openvino | mobilenetv2-12.onnx | NVIDIA GeForce RTX 3080 Ti Laptop GPU | not measured | not measured | 5.878 | inf/s/W |
| openvino-1787391710 | openvino | mobilenetv2-12.onnx | NVIDIA GeForce RTX 3080 Ti Laptop GPU | not measured | not measured | 4.462 | inf/s/W |

> Only schema-validated results are listed. Cross-runtime comparisons require identical workloads; see docs/methodology.md.
> **Perf/W is not one quantity.** `tok/s/W` rows are generative throughput per watt; `inf/s/W` rows are inferences per watt. They are not comparable to each other.