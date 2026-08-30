# AIHWBench Leaderboard

Generated from 6 validated result(s) in `results\published`.

| Run | Runtime | Model | GPU | Gen tok/s | TTFT ms | Perf/W |
| --- | --- | --- | --- | --- | --- | --- |
| llamacpp-1787391945 | llama.cpp | qwen2.5-0.5b-instruct-q4_k_m.gguf | NVIDIA GeForce RTX 3080 Ti Laptop GPU | 360.87 | 14.52 | 13.48542600896861 |
| ollama-1787388930 | ollama | qwen2.5:0.5b-instruct-q4_K_M | NVIDIA GeForce RTX 3080 Ti Laptop GPU | 110.93 | 2069.71 | 4.240443425076453 |
| onnxruntime-1787391388 | onnxruntime | mobilenetv2-12.onnx | NVIDIA GeForce RTX 3080 Ti Laptop GPU | None | None | 13.46753567139 |
| onnxruntime-1787391455 | onnxruntime | mobilenetv2-12.onnx | NVIDIA GeForce RTX 3080 Ti Laptop GPU | None | None | 11.353989914187999 |
| openvino-1787391625 | openvino | mobilenetv2-12.onnx | NVIDIA GeForce RTX 3080 Ti Laptop GPU | None | None | 5.878096883870219 |
| openvino-1787391710 | openvino | mobilenetv2-12.onnx | NVIDIA GeForce RTX 3080 Ti Laptop GPU | None | None | 4.461760364141747 |

> Only schema-validated results are listed. Cross-runtime comparisons require identical workloads; see docs/methodology.md.