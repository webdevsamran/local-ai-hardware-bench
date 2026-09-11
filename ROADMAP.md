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
      that report unavailability honestly), reachable from the CLI:
      `aihwbench bundle --sign` and `verify-bundle --verify-signature`
- [x] Typed workload engine + registry and aihwbench.workloads plugin API
- [x] Load generator (constant/closed-loop/Poisson/Gamma/burst arrivals)
- [x] Parameter sweep engine and declarative experiment manifests
- [x] Capacity ladder testing
- [x] Advanced streaming metrics and expanded statistics with guarded
      bootstrap CIs. Inter-token latency is published as a distribution
      (p50/p90/p99/max) from per-chunk arrival times, alongside `tpot_ms`,
      `time_to_second_token_ms` and `decode_duration_ms`. A mean cannot show a
      stall, and a stall is what makes a stream feel slow.
- [x] Prefill/decode separation, ISL/OSL profiles, mixed traffic,
      multi-turn and deterministic agentic workloads. The agentic workloads
      (`agentic_swe`, `agentic_data_analyst`) run a scripted loop over local,
      deterministic tools and report LLM inference time and tool execution
      time separately, with the unattributed remainder shown as overhead.
- [x] Energy measured against a verified idle baseline. The baseline is
      refused when the GPU is busy, per-token energy is null rather than zero
      when the workload's draw is below the sensor's resolution, and every
      figure states what share of gross power the workload accounted for. The
      machine state at baseline time (utilization, resident VRAM) is recorded,
      because a card still holding a model from an earlier run idles at
      roughly twice the draw of the same card after eviction — which moves
      per-token energy by two orders of magnitude with no hardware difference.
- [x] Variance enforced on the headline metric. Generation throughput must
      hold a coefficient of variation under 0.5 to pass the data-quality gate,
      and a sustained decline across a run is reported separately from noise
      by comparing the means of the run's halves. Latency variance alone was
      insufficient: it is dominated by time-to-first-token, so throughput
      could swing four-fold while latency variance stayed under 7%.
- [x] `sustained_generation` workload, plus `--prompt` and `--workload` on
      `aihwbench benchmark`. Generation throughput needs enough generated
      tokens to reach a steady state; `default_chat` asks for a two-sentence
      answer and measures mostly the GPU's clock ramp.

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
- [~] vLLM and SGLang backends over their OpenAI-compatible servers. Detection,
      streaming, usage-token accounting and metric-source labelling are
      implemented and unit-tested against a fake server; neither engine runs on
      Windows, so nothing here has been exercised against a real one. Both
      report `NOT_INSTALLED` honestly on this machine. Neither launches a
      server: startup flags (tensor parallelism, GPU memory fraction,
      quantization, KV-cache dtype) decide what is being measured.

## Track 3 — Hardware Coverage

- [x] First genuinely tested platform (i9-12900H + RTX 3080 Ti Laptop)
- [~] Vendor telemetry beyond NVIDIA. AMD (rocm-smi), Intel (RAPL) and
      Apple (powermetrics) collectors exist with tested parsers and are
      wired into the sampler; none has been run against real hardware, so
      `vendors.VENDOR_STATUS` records that per vendor. Battery telemetry
      is tested on the reference laptop. RAPL is now the sampler's power
      source of last resort, including for the idle baseline: without it a
      machine with no discrete GPU carried no energy data at all, which is
      most consumer laptops. Its scope is narrower than a GPU probe's and
      every sample says so.
- [x] NPU presence recorded in every result. No vendor exposes a portable
      utilization or power counter, so the metrics stay null — but the block
      distinguishes "this machine has no NPU" from "this machine has one and
      nothing could read it", which silence could not.
- [x] Container and image identity. A tag is not an identity, so the digest is
      recorded where the launch environment supplies it and its absence is
      explained where it does not. Never inferred from a tag.
- [ ] Intel Core Ultra NPU counters (needs Core Ultra hardware)
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
- [x] Written dispute process for published results
      ([docs/disputes.md](docs/disputes.md))
- [x] Versioned dataset snapshot manifests
- [x] Speculative decoding: draft acceptance rate, draft memory overhead and
      net speedup, distinguishing "no drafts" from "nothing accepted"
- [x] Non-text modality inventory (embedding, reranking, vision, ASR, TTS,
      image generation, speech-to-speech), each reporting its own unit
- [x] Embedding throughput across batch sizes
- [x] llama.cpp RPC backend and multi-GPU tensor-split axes, with a split
      validated against the devices the runtime actually reports
- [x] Vulkan, SYCL, WebGPU, ExLlamaV2, Jetson and ARM SBC backends:
      honest detection that names the missing half rather than reporting
      "unavailable", and no fallback to different silicon
- [x] Perplexity over a caller-supplied corpus, refusing comparisons across
      different tokenizers, corpora or run shapes
- [x] Text-to-SQL execution accuracy (Spider-shaped), read-only
- [x] Mixture-of-experts resident-vs-active memory and expert offload traffic
- [x] Cloud instance profiles as a TCO baseline (specs cited, prices not bundled)
- [x] Flash-attention on/off memory deltas across the KV-dtype matrix:
      `auto` is not `on`, and the difference is 940 MB in two of nine
      configurations
- [x] Multiple-choice evaluator (MMLU-shaped sets) that reports an answer
      it cannot read as unknown rather than as wrong
- [x] Schema 2.1 requires every field the comparison-safety classifier
      reads, so a result that cannot be compared is refused on arrival
      rather than compared anyway
- [x] Energy in kWh terms, and carbon from a caller-supplied grid intensity
- [x] Numeric quality delta per quantization against the highest-precision
      scored variant
- [x] Tokenizer-identity check: a strict comparability field that no
      backend had ever written, so silent tokenizer drift was invisible
- [x] KV-cache quantization matrix, reported as memory rather than speed
      ([docs/results/kv-cache-rtx3080ti.md](docs/results/kv-cache-rtx3080ti.md)):
      the cache size is computed from the model's own attention geometry,
      and two asymmetric configurations were measured to cost more memory
      than they save
- [x] Model zoo manifest: licence terms read from the artifact, checksums
      that state what they hash, and a download helper that deletes a
      mismatched file ([docs/models/zoo.md](docs/models/zoo.md))
- [x] Per-route code splitting that keeps static prerendering intact, with
      a per-page modulepreload for the chunk that route needs
- [x] Area, heatmap and violin charts; the heatmap renders the KV-cache
      matrix, where both inversions fall in one column
- [x] prefers-contrast, print styles, and a blanket reduced-motion rule
- [x] Desktop shell (Tauri) wrapping the same CLI and dashboard; scaffolded
      and config-tested, not yet compiled (needs a C++ linker)
- [ ] Zenodo DOI for versioned dataset snapshots: metadata and runbook
      prepared ([docs/research/minting-a-doi.md](docs/research/minting-a-doi.md));
      minting needs the maintainer's Zenodo account

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
- [x] Evaluator framework + aihwbench.evaluators entry points. Built in:
      exact match, JSON validity, cosine similarity over caller-supplied
      vectors, ROUGE-L (longest-common-subsequence overlap, order-sensitive)
      and SQuAD-style token F1 (order-insensitive). The last two are pure
      algorithms, so no dataset is bundled and nothing depends on a licence
      this repository cannot grant -- references come from the caller's JSONL.
- [~] Task-accuracy evaluators needing a corpus: perplexity, MMLU-subset,
      Spider execution accuracy. The framework and the plugin group are in
      place; each needs a dataset with a licence to redistribute, which is a
      decision about what this repository ships rather than about code.
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
      verdicts, and a pull-request validator that comments the verdict on
      submissions (`scripts/validate_pr_results.py`)
- [x] React + TypeScript production dashboard (20 routes) deployed to
      GitHub Pages from generated static dataset
- [x] The prerendered HTML actually reaches readers: the client hydrates it
      instead of calling `createRoot`, which had been discarding 53 static
      pages on every visit and falling back to a loading skeleton. Guarded by
      a hydration test that was first made to fail on the bug it describes
- [x] axe-core over all 54 prerendered pages as a CI gate, reporting what it
      could not evaluate rather than counting it as a pass; found the embed
      pages shipping with no landmark and no heading
- [x] Lighthouse 100/100/100/100 on four routes, measured and recorded with
      its conditions ([docs/research/dashboard-performance.md](docs/research/dashboard-performance.md))