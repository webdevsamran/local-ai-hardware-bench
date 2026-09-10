# Benchmark Methodology

## Principles

1. **Measure, never estimate.** A metric that cannot be captured is `null`.
2. **Record the environment.** A number without its environment is noise.
3. **Compare only like with like.** The comparison-safety classifier decides
   whether two results may be compared at all, and the exact rule set is
   published in [comparability-rubric.md](comparability-rubric.md) — generated
   from the classifier and checked in CI, so a verdict is predictable before
   you run anything and auditable afterwards.
4. **Reproducibility over peak numbers.** We prefer a slightly conservative,
   fully documented protocol over cherry-picked best-of-N.

## Controlled variables

Every benchmark run records and fixes:

| Variable | How it is controlled |
| --- | --- |
| Model + revision | model tag/digest recorded as checksum |
| Quantization | recorded in `model.quantization` |
| Context length | `--context-length` (default 2048) |
| Prompt | fixed string, recorded verbatim |
| Generated tokens | `--max-tokens` (default 128) |
| Sampling | temperature 0.0, fixed seed 42 |
| Warm-up policy | `--warmup` (default 2 runs, discarded) |
| Iterations | `--iterations` (default 5, all recorded) |
| Runtime version | recorded in `runtime.version` |
| Drivers | GPU driver recorded in `system` |
| Power profile | Windows power scheme recorded |
| Device | `--device` (auto/cpu/cuda/gpu/npu) |

## Measurement definitions

- **TTFT** — wall-clock time from request dispatch to the first streamed
  content token.
- **Prompt tok/s** — prompt token count ÷ prompt evaluation duration as
  reported by the runtime (Ollama: `prompt_eval_count`/`prompt_eval_duration`).
- **Generation tok/s** — completion token count ÷ evaluation duration as
  reported by the runtime (`eval_count`/`eval_duration`).
- **Total latency** — wall-clock request-to-final-token time.
- **Cold start** — model load time on the first warm-up request, when
  the model was not already resident. `warm_load_ms` is the mean load
  time across measured runs, and `cold_start_penalty_ms` is the
  difference: what a user waits when the model is not already in memory.
  Absent rather than zero when the model was already loaded.
- **p50/p95** — linear-interpolated percentiles across measured iterations.
- **Peak RAM/VRAM, utilization, temperature, power** — sampled every 0.5 s
  by a background telemetry thread (`psutil`, `nvidia-smi`).
- **Energy per token** — measured against an idle baseline sampled
  immediately before load, never a nameplate TDP. Two conditions must hold
  before a figure is published. The baseline must come from a quiet GPU: if
  utilization during the baseline window shows the card working, the baseline
  is refused rather than subtracted, because subtracting another process's
  draw makes the benchmark look more efficient than it is. And the workload's
  draw must exceed the baseline: when it does not, the difference is below
  the sensor's resolution and the figure is null with a reason, because
  reporting zero would claim that generating tokens is free.

  Each result also states what share of gross power the workload accounted
  for. Below 10%, the per-token figure is dominated by the baseline rather
  than the work, and the result carries a caveat saying so. This is not a
  hypothetical: the same workload on one machine measured 0.0777 J/token
  against a 14.9 W baseline and 0.0009 J/token against a 31.4 W one, because
  the second run began with a model still resident and the card at raised
  clocks. Both power readings were correct; only one of the two per-token
  figures described the workload. Results record the resident VRAM at
  baseline time so that difference is visible rather than mysterious.
- **Performance per watt** — mean throughput ÷ mean power draw. The unit
  depends on the workload: generative runtimes yield **tok/s/W**, graph and
  vision runtimes (ONNX Runtime, OpenVINO) yield **inf/s/W**, because those
  workloads emit no tokens. Every published result states which basis it
  used, and the two units must never be ranked against each other.
  Only meaningful when both are measured on the same interval.

> **This methodology has not yet been externally reviewed.** A review packet
> with the specific questions that need outside answers is at
> [methodology-review.md](methodology-review.md). The invitation is tracked in
> [`ROADMAP.md`](../ROADMAP.md) under Track 8 — issue #21 was closed because a
> reviewer cannot be summoned by leaving an issue open, not because the review
> happened.

## Known limitations (honesty section)

- Ollama's generate API reports `load_duration`, and `load_time_ms` is
  measured from it. It is null only when the model was already resident, so
  a null here means "already loaded", not "not measured".
- llama.cpp's OpenAI-compatible usage object reports token *counts* but no
  evaluation durations. Generation tok/s is therefore derived from the client
  wall-clock window between the first and last streamed content chunk, and is
  labelled `client_wall_clock` in `metrics.metric_source` — it includes the
  HTTP stack and is not comparable with an in-process engine counter such as
  `llama-bench`'s. The same applies to LM Studio, vLLM and SGLang. It is
  arguably the more useful number for this project, because it is what a
  client of a local server actually waits, but it is a different quantity and
  every result says which it is.
- Power draw via `nvidia-smi` is GPU package power, not whole-system power.
- WDDM GPU memory reporting can lag actual allocation slightly.
- Thermal analysis reads a persisted telemetry trace, so published results
  carry a throttling verdict: max and final temperature, the temperature
  slope, and time-to-throttle against an 85 C threshold. What it cannot yet
  report is peak-versus-steady-state *throughput* degradation, because the
  trace records temperature per sample and not throughput. That needs the
  sustained-load protocol (`aihwbench suite --profile sustained`), and every
  result says so in `thermal.reason` rather than leaving the fields
  unexplained.

## The machine has to be available to be measured

Every run records the CPU load sampled immediately before it starts, and a
result taken above 20% is not publishable. This is not a hypothetical
precaution.

Re-measuring ONNX Runtime on CPU during a background antivirus scan produced
**2.53 inferences per second** where the same model on the same machine had
measured **299.92** — a 118x error. OpenVINO on CPU was 78x slow in the same
window; both GPU paths were 2.3x slow, because they still need the CPU to feed
them.

All four passed every other quality check. They were consistent, so variance
was low. They were internally coherent, so plausibility was clean. Nothing in
the dataset gave them anything to be implausible against — which is exactly
the situation a contributor benchmarking new hardware is in, since there is by
definition no prior measurement to compare with.

Load is sampled *before* the run, for the same reason as the idle power
baseline: during the run the benchmark is itself the load, and the reading
would say nothing. Load that could not be measured is recorded as unknown
rather than as quiet; refusing to publish for want of an optional dependency
would be a worse rule than none.

## Statistical policy

- Report means plus p50/p95; never report a single best iteration.
- Minimum 5 measured iterations after 2 warm-ups for published results.
- Do not rank results across different model tiers or hardware classes.
- **Variance is checked on the headline metric, not only on latency.** A run
  whose generation throughput varies by more than a 0.5 coefficient of
  variation fails the data-quality gate. Latency alone was not sufficient: in
  a short-generation workload, total latency is dominated by
  time-to-first-token, so throughput can swing four-fold while latency
  variance stays under 7%.
- **A sustained decline is reported separately from noise.** Comparing the
  means of a run's two halves distinguishes a machine settling into a thermal
  or power limit -- a property worth publishing -- from a run that is simply
  noisy. It does not fail the gate: a throttling machine is a legitimate
  subject of measurement, and refusing to publish it would hide exactly the
  behaviour a buyer wants to know about.
- **Ranks within a group carry their confidence intervals.** When two results
  in one comparison group have overlapping 95% intervals, they are not
  distinguishable at that sample size and the leaderboard marks the tie. The
  rank remains as a sort order; the lead it would otherwise imply does not.
- **A prompt that stops early cannot measure a rate.** Generation throughput
  needs enough generated tokens to reach a steady state. The
  `sustained_generation` workload exists for this: `default_chat` asks for a
  two-sentence answer, which on the reference machine measured mostly the
  GPU's clock ramp (a 0.56 coefficient of variation, against 0.019 for the
  sustained workload).

## Adding a platform result

1. Run `aihwbench benchmark ...` on the target machine.
2. Validate: `aihwbench validate results/raw/<run>.json`.
3. Copy the JSON to `results/published/` and its report to `docs/reports/`.
4. Add a platform note under `platforms/<vendor>/` (drivers, BIOS, quirks).
5. Update `docs/compatibility-matrix.md` — and only then mark **Tested**.