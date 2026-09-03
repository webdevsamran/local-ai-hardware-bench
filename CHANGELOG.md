# Changelog

All notable changes to this project are documented here.
Format based on Keep a Changelog; versioning is SemVer.

## [Unreleased]
### Changed
- **Schema writer emits 2.0 via `aihwbench.versions`** — the single
  authoritative source for package/schema/protocol versions. All backends
  stamp `CURRENT_SCHEMA_VERSION`; readers still accept 1.0 and migrate
  forward. Migrations are pure (deep-copy, canonical `aihwbench.migrations`
  migrator name); `domain` parsing is strict by default (MISSING/null/
  INVALID separated, wrong-typed values no longer silently become `None`);
  anomaly detection cohorts results by comparability profile
  (protocol/runtime/model/device) with robust median/MAD statistics and a
  minimum cohort size.

### Added
- Web runtime validators (`web/src/lib/validate.ts`) with Vitest contract
  tests; `index.json` fetched once instead of twice; `trust_state` exposed
  in TypeScript types; CI adds a dependency-review job and a raised
  coverage gate.

### Fixed
### Fixed
- **Audit remediation (Phase A — P0 data-integrity/security):** see
  `docs/audit/REPOSITORY_AUDIT.md` for evidence on every item.
- Trust states unified on one canonical lowercase lifecycle
  (`unreviewed→verified/community_validated→flagged→invalidated/superseded`);
  legacy aliases and `reproducibility.trust` mapping preserved; the dataset
  export no longer mislabels verified results as `UNVERIFIED` (#trust).
- Open-loop loadgen records scheduled submit time (real queue latency);
  gamma arrivals now honor `rate_per_second` independent of shape.
- Telemetry platform-safe: Windows `ctypes` fallback guarded; per-metric
  `scope`/`source`/`device` provenance + timestamped raw trace exposed.
- `.aihwbench` verification is fail-closed: unmanifested members,
  malformed/duplicate manifest entries, oversized/high-ratio archives all
  invalidate the bundle.
- Privacy scanning unified (one recursive structured scanner in
  `sanitize.py`); findings are redacted — full secret values are never
  echoed; `quality.py` delegates.
- Backends:
  - llama.cpp uses usage-object token counters (never SSE chunk counts);
    port is OS-allocated (ephemeral) with robust cleanup.
  - LM Studio separates engine-counter metrics from client wall-clock
    rates via `metric_source`.
  - ONNX Runtime / OpenVINO feed **all** declared inputs, normalize
    dtypes, record model SHA-256 and a `graph_inputs` manifest.
- Metric vocabulary unified: canonical `METRIC_REGISTRY` in
  `metrics.py`; alias-tolerant readers in SDK/domain/exporters; the
  aggregator and CSV/SQLite/Markdown exporters emit canonical names.
- Publishing/dataset pipelines fail closed: `export --strict`, snapshot
  integrity, frontend data generation validates schema and aborts (exit 2)
  on any corrupt file.
- CI/release gates fail closed: the reusable validation workflow's
  `verdict=fail` now fails the job (configurable); regression candidate is
  selected deterministically; the release SBOM is mandatory and verified.
## [Unreleased]
### Changed
- **Package renamed:** the import package is now `aihwbench` (was
  `benchmark`). The console script and `python -m aihwbench.cli` behave
  identically; update any external imports from `benchmark.*` to
  `aihwbench.*`.

### Added
- CLI restructured into a package (`aihwbench/cli/`) with focused
  command-group modules; all subcommands and exit codes preserved.
- **LM Studio backend** (`--runtime lmstudio`): benchmarks via its
  OpenAI-compatible local server with streamed TTFT measurement; token
  counts come only from reported usage — never estimated.
- **Apple MLX backend** (detection): honest HARDWARE_REQUIRED /
  CONFIGURATION_REQUIRED states off Apple Silicon.
- **`aihwbench score` command** + `score.py`: optional composite score
  with fully published reference points, weights and component breakdown;
  renormalized when telemetry is missing, refused when throughput is
  missing. Explicitly labeled heuristic.
- New suite profiles: `rag.json` (grounded retrieval-style query) and
  `long_context.json` (8k-context comprehension).
- Makefile task runner mirroring CI commands; Dependabot now also covers
  the `web/` npm ecosystem.


### Added — top-50 platform transformation (phases 1–7)
- Collision-resistant UUID-backed run IDs with regression tests (#1).
- Corrected Linux physical-core counting and richer CPU topology
  detection with synthetic fixture tests (#2).
- Typed workload engine and registry under benchmark/workloads/ with
  id/version/input-output profiles/capability requirements (#3) and the
  aihwbench.workloads entry-point plugin API (#4).
- Parameter sweep engine (aihwbench sweep) producing structured JSON+CSV
  matrices (#5); declarative experiment manifests in JSON/TOML/YAML via
  aihwbench run (#6).
- Load generator (benchmark/loadgen/) with constant-rate, closed-loop,
  Poisson, Gamma and burst arrivals, deterministic seeds, scheduler,
  workers and recorder (#7).
- Capacity ladder (aihwbench capacity): req/s, throughput, p95/p99
  latency, TTFT, error rate, sustainable concurrency (#8).
- Advanced streaming metrics: TPOT, ITL, time-to-second-token,
  inter-chunk latency, prefill latency, decode duration, queue latency
  where measurable (#9).
- Expanded statistics: median, p50-p99.9, min/max, stddev, coefficient of
  variation, optional bootstrap CIs that refuse to fabricate confidence
  from too few samples (#10).
- Prefill/decode separated workloads and reporting (#11), standardized
  ISL/OSL length profiles (#12), weighted mixed traffic distributions
  (#13), growing-context multi-turn workloads (#14), deterministic
  agentic tool-call benchmarks (#15).
- Accuracy/evaluation framework with evaluator abstractions and small
  redistributable datasets (#16) plus the aihwbench.evaluators plugin API
  (#17); performance-quality Pareto frontier without opaque composite
  scores (#18).
- Quantization comparison (aihwbench quantization) across speed, TTFT,
  memory, power and optional quality (#19); model-fit estimator
  (aihwbench fit) clearly labeled as estimate vs fact (#20);
  recommendation engine with evidence and uncertainty (#21); bottleneck
  analyzer with explicit reasoning rules (#22); thermal stability
  analysis (peak vs steady-state, time-to-throttle) (#23).
- Energy metrics (joules/request, joules/token) with telemetry source and
  measurement tier where hardware supports it (#24); optional idle
  baseline power separating gross vs incremental power (#25); user-
  supplied cost/TCO analysis — never scraped prices (#26).
- Normalized hardware identifiers/aliases without PII (#27); device
  topology detection (PCIe, NUMA, instruction sets) (#28); multi-GPU
  representation with per-device telemetry (#29); NUMA-aware metadata
  (#30); runtime showdown comparisons (#31); runtime/driver regression
  history tracking (#32).
- env-diff (#33), reproduce prerequisite checks (#34), transparent
  reproducibility completeness score explicitly not a validity claim
  (#35), portable .aihwbench bundles with SHA-256 integrity (#36),
  provenance hashing + tamper verification (#38), thin cosign sign/verify
  interfaces that report unavailability honestly (#39).
- schema_version/protocol_version/workload_version fields with migration
  machinery preserving readers for published schema 1.0 results (#40);
  versioned dataset snapshot manifests (#41); invalidation records that
  preserve history with reasons and replacement references (#42);
  machine-readable data-quality checks (#43); z-score anomaly flags
  requesting manual review, never asserting fraud (#44).
- Public Python SDK (benchmark/sdk.py): BenchmarkResult, SystemInfo,
  RuntimeInfo, ModelInfo, MetricSet, Workload, BenchmarkRunner,
  RegressionReport (#46). Exporter plugin architecture with
  aihwbench.exporters entry points; JSON/CSV/Markdown/SQLite built-ins;
  optional Parquet behind an extra (#47). Reusable benchmark-validation
  GitHub workflow with machine-readable verdicts (#48). self-test command
  measuring timer resolution, telemetry availability, background load,
  battery vs AC, power profile, thermal state, runtime readiness (#49).
  Auto-tuner (aihwbench tune) identifying fastest/most-efficient/
  lowest-memory/balanced Pareto configurations (#50).
- Production React + TypeScript dashboard under web/: 20 routes
  (leaderboard, hardware/runtime/model/result explorers and details,
  compare, dataset explorer, methodology, compatibility matrix, docs,
  community, hardware-needed, planned enterprise/certification pages,
  about with creator attribution, 404); dependency-free SVG charts;
  accessible sortable/paginated tables; URL-shareable filters; trust
  badges; light/dark themes; skeleton/empty/error states; downloadable
  result JSON. Deterministic static dataset generation
  (scripts/generate_frontend_data.py) with CI freshness enforcement.
- CI additions: frontend lint/test/build job, generated-data freshness
  job, Pages deployment rebuilt for the Vite bundle.

### Added
- Formal JSON Schema (schemas/result_schema.schema.json, draft 2020-12)
  alongside the dependency-free semantic validator.
- Strengthened validation: run-id format, ISO-8601 UTC timestamps,
  metric range checks (non-negative; utilisation 0-100), reproducibility
  typing, iterations array checks, new optional metrics (p90/p99 latency,
  inferences/s throughput, energy per token).
- Comparison safety classifier (benchmark/comparability.py):
  STRICTLY_COMPARABLE / CONDITIONALLY_COMPARABLE / NOT_COMPARABLE with
  machine-readable reasons; compare refuses deltas for incompatible
  workloads unless --force (exit code 3).
- Backend plugin API v1: BACKEND_API_VERSION, BenchmarkMetadata, and
  third-party registration via the aihwbench.backends entry-point group.
- CLI: stable exit-code contract, doctor command, suite command with
  versioned profiles under configs/suites/, export command generating
  index.json / dataset.csv / LEADERBOARD.md from published results.
- Trust states (VERIFIED / COMMUNITY_VALIDATED / UNVERIFIED) and a
  documented community result submission pipeline.
- Fail-closed privacy scanner (benchmark/sanitize.py) covering MACs,
  IPs, SSNs, tokens, home paths, serials.
- Deterministic result fingerprints + duplicate detection.
- Statistical expansion: median/stddev/min/max latency, TTFT and TPS
  dispersion, per-metric coverage counts.
- Community infrastructure: issue templates, PR template with honesty
  checklist, CODEOWNERS, Dependabot, SUPPORT.md.
- Governance files: NOTICE, AUTHORS.md, MAINTAINERS.md, CONTRIBUTORS.md,
  GOVERNANCE.md, TRADEMARKS.md, BRANDING.md, ARCHITECTURE.md,
  docs/certification.md, docs/enterprise/overview.md,
  docs/guides/plugin-api.md, docs/results/submission-pipeline.md.

### Changed
- CI hardened: GitHub Actions pinned to immutable commit SHAs;
  ruff format --check no longer masked by '|| true'; test matrix now
  covers Python 3.10-3.13 on Ubuntu, Windows and macOS; result-schema
  job reports the number of validated files.
- Creator attribution added across CITATION.cff, pyproject metadata,
  README, NOTICE and AUTHORS.md (@webdevsamran - Original Creator).
- README restructured with audience navigation, comparison-safety and
  trust-state documentation.
- ROADMAP rewritten around nine parallel tracks.

### Fixed
- Cross-runtime comparisons no longer silently produce delta tables:
  differing runtime/backend/device/model identity is classified
  NOT_COMPARABLE (previously only model name was checked).
- llama.cpp backend executed end-to-end on CUDA (b10578 prebuilt build):
  TTFT 14.52 ms, 360.87 tok/s generation, 13.49 tok/s/W; result published.
- ONNX Runtime real benchmarking backend: model load time, latency
  percentiles, inferences/s throughput, telemetry; execution-provider
  mismatch now fails loudly instead of silently falling back.
- OpenVINO real benchmarking backend with CPU and GPU device support;
  dynamic input shapes pinned deterministically.
- Five new validated published results: llama.cpp CUDA, ONNX Runtime CPU,
  ONNX Runtime DirectML, OpenVINO CPU, OpenVINO GPU.

### Changed
- CLI `--model` is now optional; per-runtime argument validation
  (`--model` for ollama, `--model-path` for file-based runtimes).
- README runtime table and compatibility matrix updated to reflect six
  genuinely tested runtime/device combinations.

## [0.1.0] - 2026-08-22

### Added
- Cross-platform hardware detection: OS, CPU, RAM, GPU (+VRAM/driver),
  NPU enumeration, platform name — sanitized output.
- Runtime detection for 9 runtimes with explicit status states
  (AVAILABLE, NOT_INSTALLED, NOT_AVAILABLE, UNSUPPORTED_PLATFORM,
  HARDWARE_REQUIRED, CONFIGURATION_REQUIRED).
- Ollama backend: real streamed benchmarking over the local HTTP API
  (TTFT, prompt/generation tok/s from runtime statistics).
- llama.cpp backend: managed `llama-server` lifecycle + OpenAI-compatible
  streaming benchmarking with SHA-256 model checksums.
- Background telemetry sampler: peak RAM/VRAM, CPU/GPU utilization,
  temperature, power draw (psutil / nvidia-smi), performance-per-watt.
- Result schema 1.0 with dependency-free validation.
- Reproducibility block in every result (prompt, sampling params, seed,
  context length, warm-up/iterations, power profile, git commit).
- CLI: `system-info`, `detect`, `runtimes`, `benchmark`, `validate`,
  `report`, `compare`.
- Comparison tooling with comparability warnings.
- Test suite (35 tests) and GitHub Actions CI.
- Documentation: methodology, compatibility matrix, vendor collaboration,
  hardware coverage gaps, roadmap.

[0.1.0]: https://github.com/webdevsamran/local-ai-hardware-bench/releases/tag/v0.1.0