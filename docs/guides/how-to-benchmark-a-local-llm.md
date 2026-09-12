# How to benchmark a local LLM (and get a number that means something)

Measuring how fast a language model runs on your own machine is easy. Measuring
it in a way that anyone — including you, next month — can compare against
anything else is the hard part, and it is where most published local-LLM
benchmarks fall apart.

This guide covers the whole process: what to measure, how to run it, and the
five mistakes that turn a benchmark into a number with no meaning.

**Audience:** anyone running a model locally with llama.cpp, Ollama, LM Studio,
ONNX Runtime or OpenVINO who wants a defensible number, on Windows, Linux or
macOS.

## The short version

```bash
pip install -e ".[dev]"
aihwbench doctor
ollama pull qwen2.5:0.5b-instruct-q4_K_M
aihwbench benchmark --runtime ollama --model qwen2.5:0.5b-instruct-q4_K_M
aihwbench self-test
```

That produces a validated JSON document containing every measured number *and*
the conditions that produced it. The rest of this guide explains why each step
is there.

## Step 1 — Find out what you actually have

```bash
aihwbench doctor
```

`doctor` reports the CPU, GPU, VRAM, driver versions, installed runtimes and any
problems it can see — a runtime installed but not on `PATH`, a GPU with no
usable driver, a laptop on battery. Read its output before you measure
anything, because half of the surprising benchmark results people post are
explained by something `doctor` would have told them.

Two follow-ups worth running:

```bash
aihwbench runtimes
aihwbench devices
```

The first lists which runtimes are usable right now, the second enumerates the
accelerators each of them can address. On a laptop with an integrated GPU and a
discrete GPU, those are different devices with wildly different performance, and
"GPU" is not a precise enough word to record.

## Step 2 — Check the noise floor before you trust a difference

```bash
aihwbench self-test
```

This measures the environment rather than the model: timer resolution, whether
the machine is thermally throttled, what the background CPU load is, whether
power is plugged in. It exists because of a specific failure that happened
during development of this project — a 15% difference between two devices
turned out to be background CPU contention, not a property of either device.
A controlled re-run showed overlapping confidence intervals.

**If you do not know your noise floor, you cannot tell a real 10% difference
from a measurement artefact.** Most published comparisons of local LLM
performance do not report one.

## Step 3 — Run the benchmark

```bash
aihwbench benchmark --runtime ollama --model qwen2.5:0.5b-instruct-q4_K_M
```

or, against llama.cpp directly, which gives you control over the flags that
actually move the number:

```bash
aihwbench benchmark --runtime llama.cpp --model-path model-q4_k_m.gguf --device cuda
```

What happens: the harness starts the runtime if needed, runs warm-up
iterations that are excluded from the statistics, then runs the measured
iterations, sampling CPU, GPU, NPU, memory, temperature and power on a
background thread throughout. The same load generator drives every backend, so
a number from ONNX Runtime and a number from llama.cpp differ in what was
measured, not in how.

Repeat runs are the default and single runs are labelled as such. A one-shot
measurement of a system with thermal management, dynamic clocks and a page
cache is not a measurement of anything stable.

## Step 4 — Read the result, then read the conditions

```bash
aihwbench report results/raw/<run_id>.json
```

You get throughput (tokens per second, prompt and generation separately), time
to first token, inter-token latency as a distribution rather than a mean, peak
memory, and — where the hardware exposes it — power draw and energy per token.

Anything that could not be measured reliably is reported as `null` and displayed
as "not measured". It is never estimated and never silently zeroed. A zero and
an unknown are different claims about the world, and conflating them is how
benchmark tables end up asserting that a laptop drew 0 watts.

## Step 5 — Only now, compare

```bash
aihwbench compare results/raw/<a>.json results/raw/<b>.json
```

The comparison is classified before any delta is printed:

- **`STRICTLY_COMPARABLE`** — everything that moves the number matched.
- **`CONDITIONALLY_COMPARABLE`** — the workload matched, but caveats exist.
- **`NOT_COMPARABLE`** — the command refuses to print a delta and exits with
  code 3.
- **`INSUFFICIENT_METADATA`** — the fields needed to decide are missing, which
  is treated as unknown rather than as agreement.

To see exactly which fields disagree:

```bash
aihwbench env-diff <a>.json <b>.json
```

## The five mistakes

### 1. Comparing across quantizations without saying so

A q4_K_M model and a q8_0 model are different models. They produce different
output, use different memory and run at different speeds. Comparing their
tokens per second without a quality column is comparing a shortcut to the thing
it was a shortcut for. See
[choosing a quantization](choosing-a-quantization.md).

### 2. Measuring a single run

Clocks boost, then settle. Caches fill. Thermal limits engage after a few
minutes. A first run and a fifth run of the identical workload are routinely
different by more than the effect people are trying to measure.

### 3. Ignoring what else the machine is doing

A browser, a compile, an indexing service, or a second model still resident in
VRAM. This is the most common cause of an unreproducible result, and the reason
`self-test` exists.

### 4. Reporting throughput without latency

Tokens per second is throughput. What a user feels in an interactive session is
**time to first token**, then the *steadiness* of the stream. These come apart
constantly: a configuration that wins on average throughput can feel worse. See
[tokens per second, explained](tokens-per-second-explained.md).

### 5. Assuming "on the GPU" means "all of it on the GPU"

On the reference machine, `-ngl 24` on a model with 24 transformer blocks looks
like full offload and is not — the output layer stays on the CPU, and it costs
**36% of throughput**. The full measurement is in
[the offload cliff](../results/offload-cliff-rtx3080ti.md).

## What to do with a good result

Publish it. The most useful contribution to this project is a benchmark from
hardware nobody here owns:

```bash
aihwbench validate results/raw/<run_id>.json
aihwbench bundle results/raw/<run_id>.json
```

Then open a pull request. CI checks the schema, runs a fail-closed privacy scan
and verifies the integrity hashes. Nothing is uploaded from your machine until
you do this deliberately. Walkthrough:
[benchmarking your hardware](../contributing/benchmarking-your-hardware.md).

## Further reading

- [Tokens per second, explained](tokens-per-second-explained.md)
- [How much VRAM do I need?](vram-requirements-for-local-llms.md)
- [NPU vs GPU vs CPU for local AI](npu-vs-gpu-for-local-ai.md)
- [Choosing a quantization](choosing-a-quantization.md)
- [Methodology](../methodology.md) and the
  [comparability rubric](../comparability-rubric.md)
