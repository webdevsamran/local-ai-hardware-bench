# Roadmap

Milestones are adjusted to actual hardware availability. A milestone ships
when its deliverables are genuinely tested — not before.

Work is organized into parallel tracks. Nothing is marked complete until
it is real.

## Track 1 — Benchmark Core

- [x] Cross-platform hardware detection (CPU, GPU, RAM, NPU, drivers)
- [x] Runtime detection with explicit status states
- [x] Result schema 1.0 + formal JSON Schema + semantic validation
- [x] Comparison safety classifier (STRICTLY/CONDITIONALLY/NOT_COMPARABLE)
- [x] Deterministic result fingerprints + duplicate detection
- [x] Versioned suite profiles (smoke/standard/latency/throughput/efficiency/sustained)
- [ ] Model load-time measurement for Ollama (server log parsing)
- [ ] Sustained-load thermal analysis tooling (steady-state detection)
- [ ] Optional signing/attestation interface for results

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
- [ ] First-time-contributor onboarding guide
- [ ] Community discussion forums moderation guidelines

## Track 5 — Dataset & Leaderboard

- [x] Dataset generation: index.json / dataset.csv / LEADERBOARD.md
- [x] Trust states (VERIFIED / COMMUNITY_VALIDATED / UNVERIFIED)
- [ ] Trust states applied to all published results
- [ ] Static GitHub Pages leaderboard generation
- [ ] Parquet export behind an optional dependency
- [ ] Zenodo DOI for versioned dataset snapshots (when dataset matures)

## Track 6 — Enterprise Foundations

- [x] Enterprise architecture overview (documented as planned/future)
- [x] Stable exit codes for CI gates
- [ ] Baseline/regression CLI primitives (`baseline`, `regression`)
- [ ] Private storage adapter interface spec
- [ ] Fleet operation design doc

## Track 7 — Security

- [x] Actions pinned to immutable SHAs; minimal permissions
- [x] Dependabot (Actions + pip)
- [x] Fail-closed privacy scanner with tests
- [ ] CodeQL workflow
- [ ] SBOM generation in release flow
- [ ] Release checksums + provenance attestation

## Track 8 — Research / Standards

- [x] CITATION.cff with creator attribution
- [ ] Methodology review with external maintainers
- [ ] Schema 2.0 proposal with backward-compatible reader
- [ ] At least three genuinely tested hardware classes before v1.0

## Track 9 — Vendor Ecosystem

- [x] Vendor collaboration policy (no guaranteed outcomes; disclosure)
- [ ] First vendor-supplied evaluation unit processed end-to-end
- [ ] Independent reproducible benchmark report template