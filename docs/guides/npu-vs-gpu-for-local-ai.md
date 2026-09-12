# NPU vs GPU vs CPU for local AI

Every laptop sold as an "AI PC" or "Copilot+ PC" now has a neural processing
unit, quoted in TOPS, and almost none of the marketing says what it is actually
good at. This page explains where each processor wins for local inference, and
is explicit about which parts of that are architecture and which parts this
project has measured.

**Disclosure up front: no machine with an NPU has been available to this
project.** The NPU telemetry described below is written and unit-tested, and the
counter-reading mechanism was verified against an equivalent GPU counter set,
but no NPU inference result has been published here. Where this page states a
number, it says where it came from. Where it does not have one, it says that
instead. If you own an AI PC, see
[docs/hardware-needed.md](../hardware-needed.md) — one result closes this gap.

## What each processor is built for

| | CPU | GPU | NPU |
| --- | --- | --- | --- |
| **Designed for** | Branchy, serial, general work | Massively parallel arithmetic | Sustained low-power tensor ops |
| **Memory bandwidth** | Lowest (system RAM) | Highest (dedicated VRAM/HBM) | Shared with the system |
| **Power draw under load** | 15–125 W | 50–450 W | Typically single-digit watts |
| **Idle-to-busy cost** | Low | High (wakes the whole card) | Very low |
| **Good at** | Small models, orchestration, fallback | LLM decode, prefill, image generation | Background tasks, always-on features, efficiency |
| **Bad at** | Anything bandwidth-bound at scale | Battery life | Peak throughput, large models |

## Why an NPU usually loses at LLM token generation

Token generation is **memory-bandwidth-bound**, not compute-bound. To produce
one token, the model's weights have to be read out of memory — every time. What
limits you is how fast bytes move, not how many multiply-accumulates per second
the silicon can do.

That is why:

- A TOPS figure predicts NPU performance on convolutional vision workloads far
  better than it predicts LLM decode speed.
- A discrete GPU with several hundred GB/s of dedicated VRAM bandwidth beats an
  NPU sharing ~100 GB/s of system memory, at decode, more or less regardless of
  TOPS.
- The comparison flips on **prefill**, which is compute-bound, where an NPU can
  be genuinely competitive.

This is the same physics that produces the
[offload cliff](../results/offload-cliff-rtx3080ti.md): the moment weights have
to come from system RAM instead of VRAM, throughput collapses. On the reference
machine that collapse was **5.8× end to end**, with a single 39.6% step.

## Where an NPU actually wins

**Performance per watt.** This is the real pitch, and it is not a small one. An
NPU running a small model at a few watts, sustained, on battery, does something
a discrete GPU cannot: it runs all day without draining the machine or spinning
the fans.

**Leaving the GPU free.** Background transcription, noise suppression,
summarisation or a local agent running on the NPU means the GPU stays available
for whatever the user is actually doing.

**Thermal headroom.** In a thin laptop or a fanless mini PC, the GPU's peak
number is available for seconds, not minutes. Sustained throughput on hardware
that throttles is a different measurement from peak throughput, which is why
this project samples temperature and power throughout a run rather than
reporting a best-case figure.

**Small, fixed models.** Vision, speech, embeddings, rerankers — workloads that
fit comfortably and run constantly are what NPUs were designed for.

## What this project measures, and how

Where the operating system exposes counters, AIHWBench samples **NPU
utilisation during the run**, on a background thread, alongside CPU, GPU,
memory, temperature and power:

- **Windows** — the `NPU Engine` performance counter set, read per sample.
- **Linux** — the `intel_vpu` sysfs interface, as a delta between samples.

Two details that matter for trusting the result. First, the sampling happens
*during* the measured window: a reading taken after a run describes an idle
device, which is a mistake that is easy to make and impossible to notice from
the output. Second, where no counter exists — AMD's NPU exposes no utilisation
counter, and **no vendor exposes NPU power** — the field is reported as `null`
and displayed as "not measured", never as `0`.

That distinction is the reason to trust the numbers that *are* there.

## The measurement that would settle the argument

One machine, one model, three devices, the same load generator. That comparison
is already implemented and has been run on the hardware that was available:
CPU, integrated GPU and discrete GPU on the same OpenVINO IR
([study](../results/openvino-three-devices.md)). On an Intel Core Ultra, the
same backend runs a fourth way — the NPU — and the OpenVINO GenAI path here can
already target it.

What that run would produce, and nobody currently publishes:

- NPU vs iGPU vs CPU decode and prefill rates on identical silicon,
- tokens per joule for each, on battery and plugged in,
- the sustained-versus-peak gap after thermal limits engage,
- whether the NPU frees enough GPU headroom to matter for real work.

Both parts of that study — the three-device comparison and the NPU counters —
are written. The missing ingredient is an AI PC.

## Practical advice today

| If you want | Use |
| --- | --- |
| Fastest local LLM responses | Discrete GPU, model fully in VRAM |
| A 13B+ model at usable speed | Discrete GPU with enough VRAM; see [VRAM requirements](vram-requirements-for-local-llms.md) |
| All-day battery with AI features on | NPU, small models |
| Background transcription / vision while you work | NPU |
| A fanless mini PC or an SBC | NPU or integrated GPU; measure sustained, not peak |
| No GPU at all | CPU, small models at q4 — 64.4 tok/s on a 0.5B model on the reference CPU |

And whichever you pick, measure it on your own machine rather than trusting a
TOPS number:

```bash
aihwbench doctor
aihwbench devices
aihwbench benchmark --runtime openvino --model-path <model-dir> --device NPU
```

## Further reading

- [Three devices, one model](../results/openvino-three-devices.md) — CPU, iGPU and dGPU measured
- [Tokens per second, explained](tokens-per-second-explained.md) — why decode is bandwidth-bound
- [The offload cliff, measured](../results/offload-cliff-rtx3080ti.md)
- [Hardware coverage gaps](../hardware-needed.md) — what an AI PC would unlock
- [Hardware overview](../hardware/overview.md)
