# Independent Reproducible Benchmark Report - TEMPLATE

Copy this file, rename it to `<runtime>-<run_id>.md`, fill in every field
from a **real** run, and open a PR adding both the report and the raw
`results/published/<run_id>.json`. Do not submit estimated, borrowed, or
projected numbers: unavailable metrics stay `not measured`, never guessed.

---

# Benchmark Report - `<run_id>`

- **Reporter:** (your GitHub handle; independent of the result author if possible)
- **Timestamp:** (ISO-8601 UTC, copied from the result JSON)
- **Schema:** (schema_version from the result JSON)
- **Git commit:** (`git_commit` recorded inside the result JSON)
- **Reproduction check:** (paste the verdict of `aihwbench reproduce results/published/<run_id>.json`)

## System

- **OS:**
- **Platform:**
- **CPU:** (exact model string as detected by `aihwbench system-info`)
- **GPU:** (model + VRAM, or "none detected")
- **NPU:** (model, or "none detected")
- **RAM:**
- **Power profile / AC vs battery:** (from `aihwbench self-test`)

## Runtime & Model

- **Runtime:** (name + version)
- **Backend:** (backend id + device)
- **Model:** (exact tag/filename, format, quantization)
- **Checksum:** (sha256 recorded in the result JSON)

## Environment preconditions

Paste the relevant warnings/verdicts from:

```text
aihwbench doctor
aihwbench self-test
```

## Metrics

Copy the metrics table from `aihwbench report results/published/<run_id>.json`
or transcribe from the result JSON. Mark anything not captured as
"not measured".

| Metric | Value |
| --- | --- |
| Model load time | |
| Time to first token | |
| Prompt processing (tok/s) | |
| Generation (tok/s) | |
| Total latency (mean) | |
| Latency p50 | |
| Latency p95 | |
| Peak RAM | |
| Peak VRAM | |
| CPU utilization (avg) | |
| GPU utilization (avg) | |
| Max temperature | |
| Average power | |
| Performance per watt (tok/s/W) | |

## Reproducibility

Exact command(s) used:

```text
aihwbench benchmark ...
```

- Prompt:
- Max tokens / temperature / seed:
- Context length / warm-up runs / measured iterations:
- Reproducibility completeness score (`aihwbench repro-score <result.json>`):

## Deviations & caveats

List anything a reproducer would need to know: background load, thermal
conditions, driver differences, manual steps, or failed reproduction
attempts. An honest failure note is more valuable than a clean-looking
report.
