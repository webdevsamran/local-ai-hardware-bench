# The offload cliff on an RTX 3080 Ti Laptop

Measured 2026-09-10 on the reference machine (i9-12900H, RTX 3080 Ti Laptop
16 GB), llama.cpp `llama-server`, qwen2.5 0.5B instruct q4_K_M, 8 measured
iterations per point.

Raw data: [`results/sweeps/sweep-llama.cpp.json`](../../results/sweeps/sweep-llama.cpp.json)
· Reproduce with:

```bash
aihwbench sweep --runtime llama.cpp --model-path <model>.gguf --gpu-layers-list 0,6,12,18,24,99 --iterations-list 8
```

## What was measured

| GPU layers | Generation | 95% CI | Peak VRAM |
| ---: | ---: | :--- | ---: |
| 0 | 64.4 tok/s | 59.9 – 69.0 | 232 MB |
| 6 | 98.3 tok/s | 91.9 – 104.7 | 426 MB |
| 12 | 134.5 tok/s | 124.0 – 145.0 | 494 MB |
| 18 | 164.6 tok/s | 149.5 – 179.7 | 560 MB |
| 24 | 272.4 tok/s | 265.5 – 279.2 | 626 MB |
| 99 (all) | 371.9 tok/s | 359.7 – 384.0 | 632 MB |

`aihwbench cliff` reports the largest adjacent drop between 18 and 24 layers:
**39.6%**, on a curve spanning 5.8× end to end.

## Why this matters

This is the question buyers actually ask — "will a 13B model be usable on my
card?" — and it is the one a crowdsourced benchmark can answer where a vendor
benchmark cannot, because the answer is different on every machine. Where the
cliff sits depends on PCIe generation and width, memory bandwidth, and how
much VRAM the rest of the desktop is already using.

Two things in this data are worth reading carefully.

**Throughput does not degrade smoothly.** From 18 to 24 layers the rate jumps
by 65% for 66 MB more VRAM. Nothing about the memory curve predicts that
step; it is a property of where the remaining work lands.

**"All layers" is not the same as "every layer of the transformer".** 24
layers and 99 layers differ by 36%, with non-overlapping intervals. This model
has 24 transformer blocks, so `-ngl 24` looks like full offload and is not:
the output layer stays on the CPU, and it costs a third of the throughput.
Anyone tuning by counting blocks would stop one short of the answer.

## What this data cannot tell you

**It does not generalise to a bigger model.** A 0.5B model at q4_K_M needs
about 400 MB of weights, so nothing here approaches the 16 GB limit. This
curve shows the cost of *splitting* work across the PCIe bus; it does not show
what happens when a model genuinely does not fit, which is the harder and more
punishing case. Mapping that needs a model large enough to exhaust the card.

**It is one machine.** Published so someone can compare against it, not as a
figure to cite.

## A note on measurement

The first version of this sweep ran 3 iterations per point and reported 247.06
tok/s at 24 layers against 222.8 at 99 — naming 24 the best setting, which is
the opposite of what 8 iterations show. That result was noise, and
`aihwbench cliff` would have offered it as a recommendation.

It now reports which settings it cannot tell apart, using the confidence
intervals the sweep records. On this data there are none: 99 wins outright.
On the 3-iteration data it correctly declined to separate 24 from 99.

The lesson is not that 3 iterations is too few in general. It is that a
sweep's job is to compare configurations, and a comparison without a spread
attached cannot distinguish a finding from a fluctuation — which is the same
argument this project makes about the leaderboard, applied to its own tooling.
