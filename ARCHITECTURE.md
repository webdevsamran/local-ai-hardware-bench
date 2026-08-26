# Architecture

AIHWBench is a local-first, dependency-free Python framework. This
document describes the pipeline, module boundaries, and API stability
guarantees.

## Pipeline

```
CLI (aihwbench/cli/)
  -> Suite/Configuration (configs/suites/*.json, aihwbench/suites.py)
  -> System Detection (aihwbench/system_info.py)
  -> Backend/Plugin (aihwbench/backends/*)
  -> Benchmark Runner (aihwbench/runner.py)
  -> Telemetry (aihwbench/telemetry.py)
  -> Statistics (aihwbench/metrics.py)
  -> Schema Validation (aihwbench/schemas.py + schemas/*.json)
  -> Result Artifact (results/raw|published/*.json)
   -> Comparison (aihwbench/comparability.py, aihwbench/compare.py)
   -> Report/Export (aihwbench/report.py, aihwbench/export.py,
      aihwbench/exporters/*)
   -> Submission/Publication (PR pipeline; trust states in aihwbench/trust.py)
```

Supporting engines:

```
Workloads (aihwbench/workloads/)     typed definitions + registry +
                                     aihwbench.workloads entry points
Load generator (aihwbench/loadgen/)  arrival processes, scheduler,
                                     workers, recorder
Experiments (aihwbench/experiments)  declarative manifests -> sweep /
                                     capacity / showdown / tune
Evaluation (aihwbench/evaluators/)   quality evaluators + plugin API
Analysis (aihwbench/analysis/)       bottleneck, thermal, energy,
                                     cost/TCO, Pareto frontier
Provenance (aihwbench/provenance/)   hashing, bundles, cosign wrappers
Migrations (aihwbench/migrations/)   schema_version evolution
Hardware DB (aihwbench/hardware/)    normalized identifiers/topology
Quality (aihwbench/quality.py)       data-quality checks, anomalies,
                                     invalidation records
Public SDK (aihwbench/sdk.py)        typed domain objects for consumers
Static dataset (scripts/generate_frontend_data.py -> web/public/data)
Dashboard (web/)                     React SPA deployed to GitHub Pages
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
| `workloads/` | Typed workload abstractions, registry, plugin discovery | **Plugin API v1** |
| `loadgen/` | Arrival processes, request scheduler/workers/recorder | Internal |
| `evaluators/` | Quality evaluators + `aihwbench.evaluators` entry points | **Plugin API v1** |
| `exporters/` | Export formats + `aihwbench.exporters` entry points | **Plugin API v1** |
| `hardware/` | Normalized hardware identifiers, aliases, topology | Public |
| `analysis/` | Bottleneck/thermal/energy/cost/Pareto reasoning rules | Public |
| `provenance/` | Result/environment/workload/model hashing, `.aihwbench` bundles, optional cosign sign/verify | Public |
| `migrations/` | schema_version/protocol_version/workload_version evolution; readers for published schema 1.0 | Public |
| `quality.py` | Data-quality checks, anomaly flags, invalidation records | Public |
| `sdk.py` | Typed public domain objects (`BenchmarkResult`, `SystemInfo`, ...) | Public SDK |

## Stability guarantees

- **Public CLI**: subcommands and exit codes are stable within a minor
  version.
- **Plugin API v1**: `detect()`/`run()` signatures, `BackendInfo`,
  `BenchmarkConfig`, and the `aihwbench.backends` entry-point group are
  stable. Breaking changes bump `BACKEND_API_VERSION`.
- **Result schema 1.0**: published results remain readable; breaking
  schema changes require a new major version plus migration support
  (`aihwbench/migrations/`, exercised by CI against every published file).
- **Plugin APIs v1**: workload, evaluator and exporter entry-point groups
  follow the same stability rules as backends.
- **Internals** (telemetry internals, runner plumbing, loadgen internals)
  may change without notice.

## Design constraints

- Zero runtime dependencies; `psutil` is an optional telemetry extra.
- Everything works offline; no cloud calls anywhere in the core.
- Detection output is sanitized by design (no serials/MACs/usernames).
- Metrics that cannot be measured are `null`, never estimated.
- The dashboard consumes only generated static JSON derived from
  `results/published/`; charts render only when real data exists.
