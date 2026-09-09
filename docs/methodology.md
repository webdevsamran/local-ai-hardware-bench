# Benchmark Methodology

## Principles

1. **Measure, never estimate.** A metric that cannot be captured is `null`.
2. **Record the environment.** A number without its environment is noise.
3. **Compare only like with like.** The compare tool warns on any mismatch.
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
- **p50/p95** — linear-interpolated percentiles across measured iterations.
- **Peak RAM/VRAM, utilization, temperature, power** — sampled every 0.5 s
  by a background telemetry thread (`psutil`, `nvidia-smi`).
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
- llama.cpp's OpenAI-compatible usage object does not include evaluation
  durations; generation tok/s is therefore null for the llama.cpp backend
  until we parse server timing logs.
- Power draw via `nvidia-smi` is GPU package power, not whole-system power.
- WDDM GPU memory reporting can lag actual allocation slightly.
- Thermal state (laptop cooling, ambient temperature) is recorded only as
  max temperature. Sustained-throttling analysis exists in
  `aihwbench/analysis/thermal.py` but is not yet wired to a benchmark run:
  nothing persists the telemetry trace it needs, so no published result
  carries a throttling verdict.

## Statistical policy

- Report means plus p50/p95; never report a single best iteration.
- Minimum 5 measured iterations after 2 warm-ups for published results.
- Do not rank results across different model tiers or hardware classes.

## Adding a platform result

1. Run `aihwbench benchmark ...` on the target machine.
2. Validate: `aihwbench validate results/raw/<run>.json`.
3. Copy the JSON to `results/published/` and its report to `docs/reports/`.
4. Add a platform note under `platforms/<vendor>/` (drivers, BIOS, quirks).
5. Update `docs/compatibility-matrix.md` — and only then mark **Tested**.