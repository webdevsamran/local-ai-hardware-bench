# AIHWBench Leaderboard

Generated from 8 validated result(s) in `results/published`.

Results are grouped by the comparison-safety classifier (`aihwbench/comparability.py`), and **ranking is meaningful only within a group**. Putting every result in one table under a shared throughput column invites a comparison the classifier rejects for most pairs, and a footnote does not undo the claim the column makes.

7 comparable group(s); 1 contain more than one result and can be ranked.

## qwen2.5-0.5b-instruct-q4_k_m.gguf on llama.cpp (llama-server/cuda)

*Single result — nothing to compare it against yet.*

| Run | GPU | Gen tok/s | TTFT ms | Perf/W | Perf/W unit | Runs | Trust |
| --- | --- | --- | --- | --- | --- | --- | --- |
| llamacpp-1787391945 | NVIDIA GeForce RTX 3080 Ti Laptop GPU | 360.87 | 14.52 | 13.485 | tok/s/W | 5 | verified |

## qwen2.5:0.5b-instruct-q4_K_M on ollama (ollama-http-api/auto)

*Single result — nothing to compare it against yet.*

| Run | GPU | Gen tok/s | TTFT ms | Perf/W | Perf/W unit | Runs | Trust |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ollama-1787388930 | NVIDIA GeForce RTX 3080 Ti Laptop GPU | 110.93 | 2,069.71 | 4.24 | tok/s/W | 5 | verified |

## qwen2.5:0.5b-instruct-q4_K_M q4_k_m on ollama (ollama-http-api/auto)

| Run | GPU | Gen tok/s | TTFT ms | Perf/W | Perf/W unit | Runs | Trust |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ollama-1789031359-bfb62628 | NVIDIA GeForce RTX 3080 Ti Laptop GPU | 297.05 | 2,056.35 | 5.901 | tok/s/W | 8 | verified |
| ollama-1789031428-39f82fdf | NVIDIA GeForce RTX 3080 Ti Laptop GPU | 293.21 | 2,059.18 | 5.706 | tok/s/W | 8 | verified |

## mobilenetv2-12.onnx on onnxruntime (execution-providers:CPUExecutionProvider/cpu)

*Single result — nothing to compare it against yet.*

| Run | GPU | Gen tok/s | TTFT ms | Perf/W | Perf/W unit | Runs | Trust |
| --- | --- | --- | --- | --- | --- | --- | --- |
| onnxruntime-1787391388 | NVIDIA GeForce RTX 3080 Ti Laptop GPU | not measured | not measured | 13.468 | inf/s/W | 5 | verified |

## mobilenetv2-12.onnx on onnxruntime (execution-providers:DmlExecutionProvider,CPUExecutionProvider/dml)

*Single result — nothing to compare it against yet.*

| Run | GPU | Gen tok/s | TTFT ms | Perf/W | Perf/W unit | Runs | Trust |
| --- | --- | --- | --- | --- | --- | --- | --- |
| onnxruntime-1787391455 | NVIDIA GeForce RTX 3080 Ti Laptop GPU | not measured | not measured | 11.354 | inf/s/W | 5 | verified |

## mobilenetv2-12.onnx on openvino (device:CPU/cpu)

*Single result — nothing to compare it against yet.*

| Run | GPU | Gen tok/s | TTFT ms | Perf/W | Perf/W unit | Runs | Trust |
| --- | --- | --- | --- | --- | --- | --- | --- |
| openvino-1787391625 | NVIDIA GeForce RTX 3080 Ti Laptop GPU | not measured | not measured | 5.878 | inf/s/W | 5 | verified |

## mobilenetv2-12.onnx on openvino (device:GPU.0/gpu)

*Single result — nothing to compare it against yet.*

| Run | GPU | Gen tok/s | TTFT ms | Perf/W | Perf/W unit | Runs | Trust |
| --- | --- | --- | --- | --- | --- | --- | --- |
| openvino-1787391710 | NVIDIA GeForce RTX 3080 Ti Laptop GPU | not measured | not measured | 4.462 | inf/s/W | 5 | verified |

> Only schema-validated results are listed. Groups are cliques under the comparison-safety classifier: every member is comparable with every other member, not merely with the first.
> **Perf/W is not one quantity.** `tok/s/W` rows are generative throughput per watt; `inf/s/W` rows are inferences per watt. They are not comparable to each other.
> **Runs** is the measured iteration count. The published policy is 5 iterations after 2 warm-ups; anything short of it is marked, because a single measurement renders identically to a five-iteration median.
