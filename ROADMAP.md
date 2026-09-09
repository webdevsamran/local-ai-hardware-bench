# Roadmap

Milestones are adjusted to actual hardware availability. A milestone ships
when its deliverables are genuinely tested — not before.

Work is organized into parallel tracks. Nothing is marked complete until
it is real.

Markers: `[x]` done and reachable · `[~]` partially done, with the specific
gap named · `[ ]` not started. A capability that exists as a library
function but that no command or runner path calls is `[~]`, not `[x]`:
shipped-but-unreachable is not done.

## Track 1 — Benchmark Core

- [x] Cross-platform hardware detection (CPU, GPU, RAM, NPU, drivers)
- [x] Runtime detection with explicit status states
- [x] Result schema 1.0 + formal JSON Schema + semantic validation
- [x] Comparison safety classifier (STRICTLY/CONDITIONALLY/NOT_COMPARABLE)
- [x] Deterministic result fingerprints + duplicate detection
- [x] Versioned suite profiles (smoke/standard/latency/throughput/efficiency/sustained)
- [x] Model load-time measurement for Ollama (from the API's
      `load_duration` counter, not server log parsing as originally
      planned — `backends/ollama.py` emits `metrics.load_time_ms`)
- [~] Sustained-load thermal analysis tooling. The telemetry trace is now
      published in every result and `runner.py` attaches a `thermal` block
      from it, so time-to-throttle, the temperature trend and peak/final
      temperature are measured on real runs. Peak-vs-steady-state throughput
      degradation still needs per-sample throughput, which requires the
      sustained-load protocol; those fields stay null with a stated reason.
- [x] Optional signing/attestation interface (cosign sign/verify wrappers
      that report unavailability honestly)
- [x] Typed workload engine + registry and aihwbench.workloads plugin API
- [x] Load generator (constant/closed-loop/Poisson/Gamma/burst arrivals)
- [x] Parameter sweep engine and declarative experiment manifests
- [x] Capacity ladder testing
- [~] Advanced streaming metrics and expanded statistics with guarded
      bootstrap CIs. The statistics are done. Of the streaming metrics only
      `itl_ms` has a producer (`metrics.py`), and it is a scalar mean rather
      than a distribution; `tpot_ms`, `time_to_second_token_ms`,
      `inter_chunk_latency_ms`, `prefill_latency_ms` and `decode_duration_ms`
      exist as registered vocabulary and schema slots that nothing writes.
- [x] Prefill/decode separation, ISL/OSL profiles, mixed traffic,
      multi-turn and deterministic agentic workloads

## Track 2 — Runtime Ecosystem

- [x] Ollama backend: real streamed benchmarking on CUDA
- [x] llama.cpp backend (`llama-server`)
- [x] ONNX Runtime backend (CPU + DirectML EPs)
- [x] OpenVINO backend (CPU + GPU devices)
- [ ] OpenVINO GenAI LLM pipeline
- [ ] TensorRT / TensorRT-LLM backend (needs per-GPU engine builds)
- [ ] ROCm backend (Linux; needs AMD hardware)
- [ ] Lemonade / Ryzen AI backend (needs Ryzen AI hardware)
- [ ] Qualcomm QNN backend + ARM64 Windows validation (needs Snapdragon X)
- [ ] HailoRT backend, HEF benchmark configs (needs Hailo device)

## Track 3 — Hardware Coverage

- [x] First genuinely tested platform (i9-12900H + RTX 3080 Ti Laptop)
- [ ] Intel Core Ultra NPU telemetry hooks (needs Core Ultra hardware)
- [ ] AMD platform results (hardware needed)
- [ ] Snapdragon X Elite results (hardware needed)
- [ ] Mini-PC / edge device class results (hardware needed)

## Track 4 — Community

- [x] Issue templates, PR template, CODEOWNERS, SUPPORT.md
- [x] Governance document and contributor ladder
- [x] Expanded CONTRIBUTING with per-platform setup
- [x] First-time-contributor onboarding guide
- [ ] Community discussion forums moderation guidelines

## Track 5 — Dataset & Leaderboard

- [x] Dataset generation: index.json / dataset.csv / LEADERBOARD.md
- [x] Trust states (verified/unreviewed/flagged/invalidated/superseded)
      enforced by the dataset pipeline and dashboard badges
- [x] Trust states applied to all published results
- [x] Static GitHub Pages leaderboard (React dashboard generated from
      published results; data-freshness enforced in CI)
- [x] Parquet export behind an optional dependency
- [x] Invalidation records preserving history with reasons/replacements
- [x] Data-quality checks and anomaly flags for manual review
- [x] Versioned dataset snapshot manifests
- [ ] Zenodo DOI for versioned dataset snapshots (when dataset matures)

## Track 6 — Enterprise Foundations

- [x] Enterprise architecture overview (documented as planned/future)
- [x] Stable exit codes for CI gates
- [x] Baseline/regression CLI primitives (`baseline`, `regression`)
- [ ] Private storage adapter interface spec
- [ ] Fleet operation design doc

## Track 7 — Security

- [x] Actions pinned to immutable SHAs; minimal permissions
- [x] Dependabot (Actions + pip)
- [x] Fail-closed privacy scanner with tests
- [x] CodeQL workflow
- [x] SBOM generation in release flow (CycloneDX)
- [x] Release SHA256SUMS checksums
- [ ] Artifact attestation (provenance) via GitHub artifact attestations
- [x] Action-pin verification script (scripts/verify_action_pins.py)

## Track 8 — Research / Standards

- [x] CITATION.cff with creator attribution
- [ ] **Methodology review with external maintainers — not yet done.** The
      review packet is ready at
      [`docs/methodology-review.md`](docs/methodology-review.md): five specific
      questions where an outside answer would change what this project does,
      not a general invitation. What remains is a reviewer, which the
      maintainer cannot supply. Tracked here rather than as an open issue
      (#21 was closed for that reason, not because the review happened);
      `docs/methodology.md` states above its own limitations section that it
      has not been externally reviewed, and that stays until one is.

      **If you work on a runtime, benchmark hardware, or research inference
      performance and are willing to answer any of the five questions — open a
      discussion or a PR against `docs/methodology-review.md`.** Partial
      answers are useful; you do not have to take all five.
- [x] Schema 2.0 fields (schema_version/protocol_version/workload_version)
      with migration machinery and backward-compatible reader for all
      published schema 1.0 results
- [ ] At least three genuinely tested hardware classes before v1.0

## Track 9 — Vendor Ecosystem

- [x] Vendor collaboration policy (no guaranteed outcomes; disclosure)
- [ ] First vendor-supplied evaluation unit processed end-to-end
- [ ] Independent reproducible benchmark report template

## Track 10 — Platform Expansion (top-50 transformation)

- [x] Public Python SDK (benchmark/sdk.py) with typed domain objects
- [x] Exporter plugin architecture (JSON/CSV/Markdown/SQLite built-in;
      Parquet behind extra) with aihwbench.exporters entry points
- [x] Evaluator framework + aihwbench.evaluators entry points
- [x] Performance-quality Pareto frontier analysis
- [x] Quantization comparison, model-fit estimator, recommendation engine,
      bottleneck analyzer, auto-tuner
- [x] Energy metrics with telemetry tiering; idle-baseline power (measured
      before load by `runner.py`, so joules-per-token is net of the machine's
      idle draw); user-supplied cost/TCO
- [x] Normalized hardware database; PCIe/NUMA/instruction-set topology;
      multi-GPU representation
- [x] env-diff, reproduce, reproducibility completeness score
- [x] Portable .aihwbench bundles with SHA-256 integrity; provenance
      hashing and tamper verification
- [x] self-test precondition/noise checks; doctor enhancements
- [x] Reusable benchmark-validation GitHub workflow with machine-readable
      verdicts
- [x] React + TypeScript production dashboard (20 routes) deployed to
      GitHub Pages from generated static dataset