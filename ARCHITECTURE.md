# Architecture

AIHWBench is a local-first, dependency-free Python framework. This
document describes the pipeline, module boundaries, and API stability
guarantees.

## Pipeline

```
CLI (benchmark/cli.py)
  -> Suite/Configuration (configs/suites/*.json, benchmark/suites.py)
  -> System Detection (benchmark/system_info.py)
  -> Backend/Plugin (benchmark/backends/*)
  -> Benchmark Runner (benchmark/runner.py)
  -> Telemetry (benchmark/telemetry.py)
  -> Statistics (benchmark/metrics.py)
  -> Schema Validation (benchmark/schemas.py + schemas/*.json)
  -> Result Artifact (results/raw|published/*.json)
  -> Comparison (benchmark/comparability.py, benchmark/compare.py)
  -> Report/Export (benchmark/report.py, benchmark/export.py)
  -> Submission/Publication (PR pipeline; trust states in benchmark/trust.py)
```

## Module responsibilities

| Module | Responsibility | Stability |
| --- | --- | --- |
| `cli.py` | Argument parsing, exit codes, command dispatch | Public CLI contract |
| `exit_codes.py` | Stable exit codes for CI automation | Public contract |
| `system_info.py` | Sanitized hardware/OS detection | Public |
| `backends/base.py` | Plugin types: `BackendInfo`, `BenchmarkConfig`, `BenchmarkMetadata`, statuses | **Plugin API v1** |
| `backends/__init__.py` | Registry + entry-point discovery (`aihwbench.backends`) | **Plugin API v1** |
| `backends/<runtime>.py` | One runtime each; `detect()` never raises, `run()` raises `BackendError` cleanly | Plugin API v1 |
| `runner.py` | Orchestrates a run; enriches reproducibility metadata | Internal |
| `telemetry.py` | Background sampling of RAM/VRAM/util/temp/power | Internal |
| `metrics.py` | Percentiles, dispersion, derived metrics from measured values only | Internal |
| `schemas.py` | Authoritative semantic validation (types, ranges, formats) | Public (schema 1.0) |
| `comparability.py` | STRICTLY/CONDITIONALLY/NOT_COMPARABLE classification | Public |
| `compare.py` | Metric deltas guarded by the classifier | Public |
| `fingerprint.py` | Deterministic experiment fingerprints; duplicate detection | Public |
| `sanitize.py` | Fail-closed privacy scanning of artifacts | Public |
| `trust.py` | VERIFIED / COMMUNITY_VALIDATED / UNVERIFIED states | Public |
| `suites.py` | Versioned suite profiles under `configs/suites/` | Public |
| `export.py` | index.json / dataset.csv / LEADERBOARD.md generation | Public |

## Stability guarantees

- **Public CLI**: subcommands and exit codes are stable within a minor
  version.
- **Plugin API v1**: `detect()`/`run()` signatures, `BackendInfo`,
  `BenchmarkConfig`, and the `aihwbench.backends` entry-point group are
  stable. Breaking changes bump `BACKEND_API_VERSION`.
- **Result schema 1.0**: published results remain readable; breaking
  schema changes require a new major version plus migration support.
- **Internals** (telemetry internals, runner plumbing) may change
  without notice.

## Design constraints

- Zero runtime dependencies; `psutil` is an optional telemetry extra.
- Everything works offline; no cloud calls anywhere in the core.
- Detection output is sanitized by design (no serials/MACs/usernames).
- Metrics that cannot be measured are `null`, never estimated.