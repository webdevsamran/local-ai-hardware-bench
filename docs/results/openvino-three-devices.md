# Three devices, one model, one machine

Raw data: [`results/measurements/openvino-three-devices.json`](../../results/measurements/openvino-three-devices.json)

The same OpenVINO IR — `OpenVINO/Qwen2.5-Coder-0.5B-Instruct-int4-ov`,
`int4_asym` with group size 128 — run on an Intel CPU, an Intel integrated GPU
and a discrete NVIDIA GPU, consecutively, in one process, on one machine.
OpenVINO GenAI 2026.3.1, 5 measured iterations after a warm-up, greedy
decoding, 64 tokens.

This is the comparison nothing else in the project could make: every other LLM
backend here targets one vendor's silicon, so the model always changed when the
device did.

## The measurements

| Device | tok/s | 95% CI | TTFT | ITL p50 | Load | Power |
|---|---|---|---|---|---|---|
| i9-12900H (CPU) | 74.98 | 71.27 – 78.68 | 62 ms | 13.2 ms | 3.7 s | 28.8 W |
| Iris Xe (iGPU) | 75.97 | 68.94 – 83.00 | 72 ms | 12.5 ms | 7.5 s | 29.3 W |
| RTX 3080 Ti (dGPU) | 19.64 | 17.38 – 21.90 | 332 ms | 44.6 ms | 9.1 s | 50.2 W |

**These are not published results.** Background CPU ranged from 5% to 28%
across the three runs, against this project's own 20% threshold. They are
recorded because two of the three findings below do not depend on the absolute
numbers at all.

## The CPU and the integrated GPU are indistinguishable

74.98 tok/s against 75.97, with intervals overlapping across nearly their whole
width. On this model, on this machine, moving the work to the iGPU buys
nothing — and costs twice the load time.

It is worth saying what this is *not*. An earlier pass of this same sweep,
taken while two unrelated test suites were running, appeared to show the CPU
ahead by 15%, and it would have been easy to write that up as "the CPU wins".
It was noise. The intervals are the reason this version does not make that
claim, and the reason the first version should not have.

## Greedy decoding is not reproducible on the iGPU

Six greedy generations from the same prompt:

| Device | Distinct outputs |
|---|---|
| CPU | 1 |
| Iris Xe | **4** |

Greedy decoding takes the highest-probability token at every step, so it is
deterministic by definition. Four different answers means the device's kernels
produce slightly different logits from run to run — parallel reductions need
not sum in the same order — and near-ties flip the argmax.

This matters more than the throughput figures, and it does not depend on
timing, so contention cannot explain it away. Any quality comparison that
assumes a fixed seed and greedy decoding yields one answer is wrong on this
device. The project's own fidelity probe reports it (`deterministic: false`),
which is exactly what that probe is for.

## Routing to the discrete GPU through OpenVINO costs 4× the speed and 2× the power

19.64 tok/s at 50.2 W, against 74.98 tok/s at 28.8 W on the CPU. Time to first
token is five times longer.

**This is a statement about OpenVINO's path to the card, not about the card.**
OpenVINO reaches an NVIDIA GPU through a generic route rather than CUDA. The
comparison that would say what the card can actually do is llama.cpp with a
CUDA build — a different runtime and a different quantization, so no number
from it is quoted here.

The useful lesson is narrower and more practical: *"runtime X supports your
GPU"* and *"runtime X is a good way to use your GPU"* are different claims, and
a device list cannot tell them apart. This is the only device of the three
where the memory figure is real (658 MiB), because it is the only one
`nvidia-smi` can see.

## Memory on the integrated GPU was not measured

The iGPU row has no `peak_vram_mb`, and that is deliberate. Telemetry reads
`nvidia-smi`, which reports the NVIDIA card whatever the run was on; an Intel
iGPU allocates from shared system RAM, where that tool cannot see it. Reporting
the idle NVIDIA card's `0.0` would have said this model needs no memory. The
field is absent and `metrics.metric_source` says why.

## Reproducing this

```bash
pip install "aihwbench[openvino]"
huggingface-cli download OpenVINO/Qwen2.5-Coder-0.5B-Instruct-int4-ov --local-dir ./qwen-ov
aihwbench benchmark --runtime openvino_genai --model-path ./qwen-ov --device cpu
aihwbench benchmark --runtime openvino_genai --model-path ./qwen-ov --device GPU.0
```

Run them on an idle machine if you want the throughput figures to mean
anything. The determinism check needs nothing but a repeated greedy generation.
