# How much VRAM do I need to run a local LLM?

The question behind most GPU purchases for local AI, and the one where
estimates are most often quoted as if they were measurements.

This page gives you the arithmetic, the part of it the arithmetic misses, and
what actually happens when a model does not fit — which, on the reference
machine, was measured rather than guessed.

## The estimate

Three things occupy VRAM while a model runs:

**1. Weights.** Roughly `parameters × bytes-per-parameter`:

| Quantization | Bytes/param | 7B | 13B | 34B | 70B |
| --- | ---: | ---: | ---: | ---: | ---: |
| FP16 | 2.0 | ~14 GB | ~26 GB | ~68 GB | ~140 GB |
| q8_0 | ~1.06 | ~7.4 GB | ~14 GB | ~36 GB | ~74 GB |
| q6_K | ~0.82 | ~5.7 GB | ~11 GB | ~28 GB | ~57 GB |
| q5_K_M | ~0.71 | ~5.0 GB | ~9.2 GB | ~24 GB | ~50 GB |
| q4_K_M | ~0.64 | ~4.5 GB | ~8.3 GB | ~22 GB | ~45 GB |
| q3_K_M | ~0.51 | ~3.6 GB | ~6.6 GB | ~17 GB | ~36 GB |

These are approximations. Real GGUF files vary by a few percent because
different tensors get different treatment — attention and embedding tensors are
commonly kept at higher precision than the bulk of the weights.

**2. KV cache.** This is the part people forget, and it grows with *context
length*, not with model size alone. At long context it can rival the weights.
`f16` is the default; quantizing the cache cuts it substantially.

**3. Overhead.** Compute buffers, the CUDA/ROCm/Metal context itself, the
framework's allocator, and — on a desktop — whatever the display and browser
are already using. Budget 1–2 GB before you have loaded anything.

Rule of thumb: **weights + KV cache + ~1.5 GB, and leave headroom.** A 7B at
q4_K_M is comfortable on 8 GB at moderate context, tight on 6 GB, and does not
fit alongside a browser on 4 GB.

Get a calculated estimate, explicitly labelled as an estimate:

```bash
aihwbench fit --parameters 7B --quantization q4_k_m
```

The interactive version, which also surfaces any *measured* results for that
configuration, is the
[Will it run on my PC?](https://webdevsamran.github.io/local-ai-hardware-bench/will-it-run)
page.

## What the estimate misses

An estimate tells you whether the model fits. It does not tell you how fast it
runs, and the relationship between "fits" and "fast" is not linear — it is a
step.

On the reference machine (RTX 3080 Ti Laptop 16 GB, PCIe), sweeping the number
of layers kept on the GPU produced this:

| GPU layers | Generation | 95% CI | Peak VRAM |
| ---: | ---: | :--- | ---: |
| 0 | 64.4 tok/s | 59.9 – 69.0 | 232 MB |
| 6 | 98.3 tok/s | 91.9 – 104.7 | 426 MB |
| 12 | 134.5 tok/s | 124.0 – 145.0 | 494 MB |
| 18 | 164.6 tok/s | 149.5 – 179.7 | 560 MB |
| 24 | 272.4 tok/s | 265.5 – 279.2 | 626 MB |
| 99 (all) | 371.9 tok/s | 359.7 – 384.0 | 632 MB |

Two things in that table are worth more than the estimate:

**Throughput does not degrade smoothly.** Between 18 and 24 layers the rate
jumps 65% for 66 MB more VRAM. The largest adjacent drop is **39.6%**, on a
curve spanning **5.8×** end to end. Nothing in the memory column predicts where
that step falls — it depends on PCIe generation and width, memory bandwidth, and
what else is using the card. That is why it has to be measured per machine.

**"All layers" is not "every layer of the transformer."** This model has 24
blocks, so `-ngl 24` looks like full offload. It is not: the output layer stays
on the CPU, and those last 36% of throughput are sitting right there.

Full study: [the offload cliff](../results/offload-cliff-rtx3080ti.md). Find
the cliff on your own machine:

```bash
aihwbench sweep --runtime llama.cpp --model-path <model>.gguf --gpu-layers-list 0,8,16,24,32,99
aihwbench cliff results/sweeps/<sweep-file>.json
```

## Shrinking the KV cache

If the weights fit but long context does not, the KV cache is what to attack —
and the results here are counter-intuitive enough that they were measured
across all nine K/V dtype combinations at 32K context:

| K | V | cache | vs f16 | device VRAM | tok/s vs f16 |
| --- | --- | ---: | ---: | ---: | ---: |
| q4_0 | q4_0 | 108 MiB | −71.9% | 748 MiB | +0.0% (noise) |
| q8_0 | q8_0 | 204 MiB | −46.9% | 844 MiB | −2.3% (noise) |
| q8_0 | q4_0 | 156 MiB | −59.4% | 764 MiB | **−62.1%** |
| f16 | q4_0 | 246 MiB | −35.9% | 854 MiB | **−66.1%** |
| f16 | f16 | 384 MiB | — | 1022 MiB | — |

**Use the same dtype for K and V.** `q4_0` for both cut cache memory by 71.9%
with a throughput difference inside the noise floor. Every *asymmetric*
configuration measured was worse than both symmetric ones it sits between —
some of them catastrophically, losing over 60% of throughput for less memory
saved than the symmetric option that costs nothing.

And note what this is: **a memory feature, not a speed feature.** KV-cache
quantization buys you context length, not tokens per second. Full study:
[KV-cache quantization](../results/kv-cache-rtx3080ti.md).

```bash
aihwbench kv-cache results/sweeps/sweep-llama.cpp-kvcache.json --model-path <model>.gguf
```

## Unified memory is a different problem

On Apple Silicon and on AMD/Intel integrated graphics, there is no separate
VRAM pool — the GPU and CPU share system memory, so "does it fit" becomes "how
much of your RAM are you willing to give it", and the bandwidth story changes
completely. AIHWBench has a written MLX backend for this case, but **no Apple
Silicon machine has been available to run it**, so this guide deliberately
quotes no numbers for it. If you have one, see
[docs/hardware-needed.md](../hardware-needed.md) — a single result would close
that gap.

## Practical guidance by VRAM tier

| VRAM | Comfortable | Possible with care | Don't |
| --- | --- | --- | --- |
| 4 GB | 1–3B at q4 | 7B at q3, short context | 13B |
| 6 GB | 7B at q4, short context | 7B at q4, longer context with quantized KV | 13B at usable speed |
| 8 GB | 7B at q4–q5 | 13B at q4, short context | 34B |
| 12 GB | 13B at q4 | 13B at q5–q6 | 70B |
| 16 GB | 13B at q5, 7B at q8 | 34B at q3, short context | 70B |
| 24 GB | 34B at q4 | 34B at q5 | 70B at usable speed |
| 48 GB+ | 70B at q4 | 70B at q5 | — |

Treat this table as a starting point and measure, not as a result. It is
arithmetic plus experience, not data from this project — and the difference
between those two things is the whole reason this project exists.

## Further reading

- [Will it run on my PC?](https://webdevsamran.github.io/local-ai-hardware-bench/will-it-run) — interactive, backed by measured results where they exist
- [The offload cliff, measured](../results/offload-cliff-rtx3080ti.md)
- [KV-cache quantization, measured](../results/kv-cache-rtx3080ti.md)
- [Choosing a quantization](choosing-a-quantization.md)
- [Tokens per second, explained](tokens-per-second-explained.md)
