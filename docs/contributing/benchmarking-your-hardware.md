# Benchmarking your own hardware

This dataset is only as broad as the machines people run it on, and the
maintainers own one. If you have hardware that is not in
[`compatibility-matrix.md`](../compatibility-matrix.md) — an Apple silicon
Mac, a Snapdragon X laptop, a Jetson, an AMD GPU, a desktop RTX card, a
Raspberry Pi — a result from it is the single most useful thing you can
contribute.

There are two ways to produce one.

## By hand

```bash
pip install aihwbench
aihwbench doctor                     # what this machine can reach
aihwbench benchmark \
  --runtime ollama \
  --model qwen2.5:0.5b-instruct-q4_K_M \
  --workload sustained_generation \
  --iterations 8 --warmup 3
aihwbench validate results/raw/<run>.json --formal
aihwbench quality  results/raw/<run>.json
```

Then open a pull request adding the JSON to `results/published/`, or attach it
to a [benchmark submission
issue](https://github.com/webdevsamran/local-ai-hardware-bench/issues/new?template=benchmark-submission.yml).

## With the GitHub Action

If you would rather have it reproducible and logged, register your machine as
a [self-hosted
runner](https://docs.github.com/en/actions/hosting-your-own-runners) and use
the action:

```yaml
name: Benchmark my hardware
on: workflow_dispatch

jobs:
  bench:
    runs-on: self-hosted
    steps:
      - uses: webdevsamran/local-ai-hardware-bench/.github/actions/run-benchmark@main
        with:
          runtime: ollama
          model: qwen2.5:0.5b-instruct-q4_K_M
          workload: sustained_generation
```

It installs the tool, records what your machine is, runs the benchmark,
validates the result against the schema, runs the data-quality checks, scans
for anything private, and uploads the result as an artifact.

### What it will not do

**It will not open a pull request or publish anything.** Publishing sets a
result's trust state, and a machine cannot review its own measurement.
Submitting is your decision, and the result arrives as `unreviewed`.

**It will not run on a GitHub-hosted runner.** A shared virtual machine has no
power telemetry, no stable thermal behaviour, and neighbours competing for the
same silicon. Numbers from one describe the datacentre's scheduling rather
than hardware anyone owns, so the action refuses rather than producing a
plausible number nobody should trust. `allow-hosted-runner: true` exists to
exercise the pipeline, not to produce a result.

## Why the defaults are what they are

**`workload: sustained_generation`, not the default chat prompt.** The default
prompt asks for an answer "in two sentences", so it generates about 29 tokens
however high `--max-tokens` goes. That is too little work to measure a
generation *rate*: on the reference machine the per-iteration figure ran 327,
342, 118, 124, 84 tok/s as the GPU ramped its clocks — a mean of 199 tok/s
that the machine never sustained for a moment. The sustained workload
generates enough to reach a steady state.

**Eight iterations after three warm-ups.** Five measured iterations is the
published minimum; eight leaves room for one to land badly without the run
becoming unpublishable.

## If the quality gate fails

The action fails the job when a result does not pass every data-quality check.
That is deliberate: it is far better to catch an unstable measurement on the
machine that produced it than to have it argued over in a pull request.

**The first thing to check is `measured_on_an_idle_machine`.** A benchmark
measures your hardware only when your hardware is free to be measured. This is
not a formality: re-measuring ONNX Runtime on CPU during a background
antivirus scan produced 2.53 inferences per second where the same model on the
same machine had measured 299.92 — a 118x error that passed every other check,
because it was consistent and internally coherent and there was nothing to
compare it against.

Close what you can, wait for any scan or indexer to finish, and re-run. The
result records the CPU load it measured, so you can see what it was competing
with.

The next check contributors hit is `variance_acceptable`, and the reason is
usually fixable:

- **Other work on the GPU.** A browser with hardware acceleration, a game
  launcher, another model still resident. Close them and re-run.
- **Too little work per iteration.** If you overrode `workload` or
  `max-tokens`, the run may be measuring clock ramp rather than throughput.
- **A monotonic decline** — throughput falling across the run and not
  recovering. This one is not a mistake. It means your machine is settling
  into a thermal or power limit, which is a real and interesting property of
  the hardware. Say so in the submission; a laptop that cannot hold its peak
  rate is exactly the thing buyers want to know and nobody publishes.

## What gets recorded, and what does not

`aihwbench detect` sanitizes as it collects: no serial numbers, no MAC
addresses, no home directory paths, no user names. The action runs an
independent privacy scan before the upload, because the upload is what would
publish a leak.

What is recorded is your CPU and GPU model, RAM, OS version, driver version,
the runtime and model identity, and the measurements. If you would rather
check before submitting, run `aihwbench redact <result>.json` and compare.
