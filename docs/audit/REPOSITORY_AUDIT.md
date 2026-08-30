# AIHWBench Repository Audit

> **HEAD audited:** `d1503a0` (pre-remediation baseline on `main`)
> **Audit branch:** `audit/remediation-phase-a` (fixes listed with commit hashes)
> **Audit date:** 2026-08-29
> **Scope:** every tracked source, test, workflow, schema, doc, generated
> dataset definition, frontend file, result artifact, and license/governance
> file. Lockfiles/generated JSON were inspected structurally for drift.
> **Baseline:** 203 tests passed / 1 skipped; ruff clean; `--cov-fail-under=55`.

## Summary

AIHWBench is a genuinely useful, dependency-free local benchmark. The audit
found **9 P0 data-integrity/security defects** — all confirmed against HEAD
with evidence, not inferred from README claims. All 9 are now fixed on the
remediation branch with regression tests. P1/P2 architectural and hygiene
defects (schema versioning, formal-schema drift, migrations purity,
anomaly/comparability semantics, fingerprint coverage, capacity-doc
mismatch, frontend routing/data-layer, docs drift, CI hardening) are
documented with fixes planned in Phases B–D.

Nothing in this document was fabricated: every finding cites the file and
line observed at HEAD, and every fix cites its commit and test.

---

## P0 — Correctness / data integrity / security (all verified, all fixed)

### P0-1. Two incompatible trust-state systems

**Evidence (`d1503a0`).** `aihwbench/trust.py` defined `VERIFIED /
COMMUNITY_VALIDATED / UNVERIFIED` (uppercase); `aihwbench/quality.py`
used lowercase `unreviewed / verified / flagged / invalidated /
superseded` with no `community_validated`. Published results carried both
`reproducibility.trust: "VERIFIED"` and top-level `trust_state:
"verified"`. `export.py` read only the legacy field via a normalizer whose
unknown-value default was the uppercase `UNVERIFIED`, so **all six
published results surfaced as `UNVERIFIED` in `results/dataset/` even
though each document says `verified`**. README, CLI, exporters, frontend
and the JSON Schema each used a different vocabulary.

**Impact.** Data-trust signals were wrong in the canonical dataset;
downstream consumers could not rely on a single trust lifecycle.

**Fix — commit `49e1788`.** One canonical lowercase lifecycle
(`unreviewed → verified / community_validated → flagged →
invalidated / superseded`) in `trust.py`; legacy constant *names* kept as
aliases to canonical *values* (source compatibility); `effective_trust()`
reads the authoritative top-level `trust_state` first and maps legacy
`reproducibility.trust` deterministically; `quality.py`, `export.py`,
`scripts/build_dataset_views.py` and the legacy normalizer all delegate to
it. Export outputs regenerate deterministically (the only dataset delta
was the trust column — previously wrong).

**Tests.** `tests/test_trust_lifecycle.py` (lifecycle transitions,
legacy mapping, effective resolution precedence, unknown-value handling).

---

### P0-2. Open-loop loadgen discards scheduled submit time

**Evidence (`d1503a0`).** In `aihwbench/loadgen/__init__.py` `_pool_worker`
recorded `RequestRecord(request_id, start, start, ...)` — both `submit_time`
and `start_time` set to the moment the worker picked up the request. The
scheduled arrival timeline (the `pending` queue) was discarded, making
measured queue latency exactly zero under saturation.

**Impact.** Capacity/serving benchmarks reported zero queue latency even when
requests were queued.

**Fix — commit `ac60da6`.** Workers now record the scheduled `submit_at`
captured at enqueue time; queue latency = `start - submit` and is real.
Determinism preserved (seeded arrivals and identical configs reproduce
identical sequences).

**Tests.** `tests/test_loadgen_timing.py` (nonzero queue latency under
saturation, determinism, keep-alive timing invariants).
---

### P0-3. Gamma arrivals change the mean rate with shape

**Evidence (`d1503a0`).** Inter-arrivals used
`random.gammavariate(shape, 1/rate)`, whose mean is `shape/rate`, so
`rate_per_second` was silently the *rate times the shape*.

**Impact.** A documented 10 req/s gamma load with shape 4 actually arrived
at ~40 req/s.

**Fix — commit `ac60da6`.** Gamma inter-arrivals are scaled to
`1/(rate * shape)` so the mean arrival rate equals `rate_per_second` for
any shape.

**Tests.** `tests/test_loadgen_timing.py::test_gamma_rate_independent_of_shape`
(persists for shapes 0.5 and 4.0).

---

### P0-4. Telemetry: unguarded Windows fallback + missing scope/source

**Evidence (`d1503a0`).** `_system_ram_mb` fell back to
`ctypes.windll.kernel32.GlobalMemoryStatusEx` on **any** platform when
`psutil` was absent (breaking on Linux/macOS); there was no platform guard.
All summaries were unnamed metrics — system-wide RAM/CPU, first NVIDIA GPU
only, NVIDIA board power — that could be read as process or whole-system
values.

**Fix — commit `ac60da6`.** Windows-only fallback now requires
`sys.platform == "win32"`; every platform path is defensive. `TelemetrySampler`
exposes per-run `provenance()` (scope/source/device for RAM/CPU/GPU),
a top-level `telemetry` block consumers can emit into results, and a
timestamped `raw_trace()` array (explicitly separate from summaries).
Backends (ollama/llama.cpp/lmstudio/onnxruntime/openvino) now attach
`telemetry` provenance to results.

**Tests.** `tests/test_telemetry_scope.py` (provenance shape, trace
timestamping, monotonic samples, platform-guard logic under simulated
non-Windows).

---

### P0-5. `.aihwbench` bundle verification accepts injected members

---

### P0-7. llama.cpp counts SSE chunks as tokens and hard-codes port 8123

**Evidence (`d1503a0`).** Each SSE `choices[0].delta.content` chunk was
accumulated and then written as `completion_tokens` — a transport chunk is
not a guaranteed token; the resulting `generation_tokens_per_second` was
inflated. The llama.cpp server port was `8123` (collision-prone).

**Fix — commit `1f3599e`.** `completion_tokens` / `eval_seconds` now come
**only** from the OpenAI-compatible `usage` object when present; the chunk
count is exposed as a clearly non-token field (`content_chunks`) with an
explicit `metric_source` block stating it is a chunk count, never a token
count. Server port is allocated from an ephemeral range (OS-assigned) and
cleanup is robust on all exit paths.

**Tests.** `tests/test_backend_contracts.py`
(`test_llama_cpp_uses_usage_tokens_not_stream_chunks` — feeds a mock SSE
stream with more chunks than usage tokens and asserts the token metric
equals the usage count; ephemeral-port allocation; cleanup on error).

---

### P0-8. LM Studio writes wall-clock rate into engine-counter field

**Evidence (`d1503a0`).** Docstring stated "token counts come only from
reported usage — never estimated", yet the backend placed a
client-wall-clock-derived `tokens per second` into the engine-counter field
`generation_tokens_per_second`.

**Fix — commit `1f3599e`.** LM Studio now separates metrics by source: the
engine counter stays in `generation_tokens_per_second` when the runtime
reports `usage.completion_tokens` + equivalent durations; the client
wall-clock rate is exposed under a distinctly labeled `metric_source` block
(`client_wall_clock`) and is never merged into the engine counter.

**Tests.** `tests/test_backend_contracts.py`
(`test_lmstudio_metric_source_separates_engine_and_wall_clock`).

---

### P0-9. ONNX Runtime and OpenVINO feed only the first input

**Evidence (`d1503a0`).** Both graph backends built a full input feed but
executed only `inputs[0]` — multi-input models were mis-measured or failed;
dtype handling was narrow and no model-identity hash was recorded.

**Fix — commit `1f3599e`.** `resolve_input_specs` (in `backends/base.py`)
resolves **every** declared input (dynamic dims pinned to 1, dtype
normalization across runtime vocabularies, fail-closed on unsupported
dtypes such as bfloat16); both runtimes feed all inputs; a streaming
`file_sha256` of each model file is recorded as `model.checksum`, and the
declared-input manifest (`graph_inputs`) is recorded verbatim in
`reproducibility` so readers can audit the feed.

**Tests.** `tests/test_backend_contracts.py` (resolver covers every declared
input, dtype normalization, dynamic-shape pinning, file_sha256; both
backends wired through the resolver).

---

### P0-10. Export/dataset pipelines silently drop data (fail-open)

**Evidence (`d1503a0`).** `scripts/generate_frontend_data.py` WARN-skipped
unreadable JSON; `export.load_results` and `dataset_versioning` silently
`continue`d past unreadable/invalid files; CI published from the leftover
subset. `exporters/_flat_row` also used a different (legacy) metric
vocabulary than the schema — the CSV/SQLite/Markdown plugin exporters
produced empty latency/energy columns.

**Fix — commits `0a6e6e5` and `4583444`.**
- **Metrics:** one canonical `METRIC_REGISTRY` (id → unit/family/aliases);
  `resolve_metric()` reads canonical-first with legacy-alias fallback so old
  documents never lose data; the aggregator emits canonical names only;
  `sdk.MetricSet`, `domain.MetricSet`, and the plugin exporters all read
  through the registry; `CSV_COLUMNS` uses canonical ids. Tests:
  `tests/test_metric_aliases.py`.
- **Pipelines:** `load_results(..., strict=True)` (and
  `export_dataset(..., strict=True)`) fail closed with `DatasetLoadError`;
  the CLI export command gained `--strict`; the snapshot builder aborts on
---

## P1 — Schema, contracts, architecture (verified; fixes planned)

| # | Finding (evidence at HEAD) | Impact | Planned fix |
| --- | --- | --- | --- |
| P1-1 | Version authority fragmented: `__init__.py` `SCHEMA_VERSION="1.0"`, `schemas.py` writer 2.0, backends emit `__init__.SCHEMA_VERSION`. | Confusing public contract. | Authoritative version source + explicit reader/writer versions (B). |
| P1-2 | `schemas/result_schema.schema.json` is formal schema 1.0 with `additionalProperties: true` at every block; semantic validator accepts 1.0/2.0. | Contract drift invisible to formal validation. | Versioned formal schemas (`result-1.0`, `result-2.0`) + contract tests (B). |
| P1-3 | `migrations/__init__.py` references `benchmark.migrations._migrate_1_to_2` (pre-rename) and shallow-copies via `dict(data)`. | Can mutate nested input state. | Pure/idempotent deep-copy migrations + version-path tests (B). |
| P1-4 | `domain.py` coerces wrong-typed values to `None`; CI tuples can contain `None`. | Corruption reads as "not measured". | MISSING/null/INVALID tri-state + strict/lenient modes (B). |
| P1-5 | Anomaly detection z-scores heterogeneous populations. | Statistically meaningless flags. | Cohort by comparability profile, median/MAD, min-N (B). |
| P1-6 | Fingerprint omits `protocol_version`/environments; can flag legitimate repeats. | False duplicates. | Versioned fingerprint v2 (B). |
| P1-7 | `capacity.py` docstring says lowest-concurrency baseline but code uses min p95. | Undocumented methodology. | Pick one rule, test it, document (B). |
| P1-8 | No comparison profiles; strict runtime/device mismatch vs heterogeneous leaderboard. | Ranks incomparable results. | Comparison profiles + science cohorts (B). |
| P1-9 | Frontend hardware fingerprint = CPU/GPU/NPU hash only (`generate_frontend_data.py:49-52`). | Merges distinct systems. | Versioned fingerprint v2 (B). |

## P2 — Frontend / hygiene / docs truth

| # | Finding (evidence) | Status |
| --- | --- | --- |
| P2-1 | Frontend fetches `index.json` twice (`web/src/lib/data.ts:16,31`); all six datasets eagerly loaded. | Planned (D). |
| P2-2 | Frontend TS types hand-duplicated and stale; no runtime validation. | Planned (D). |
| P2-3 | `web/tsconfig.tsbuildinfo` tracked; `web/.gitignore` lacks `*.tsbuildinfo`. | Planned (D). |
| P2-4 | `BrowserRouter` on GitHub Pages with `/local-ai-hardware-bench/` → deep-link 404s. | Planned (D): HashRouter (ADR-0006). |
| P2-5 | README/ROADMAP/SECURITY disagree on SBOM/Parquet/thermal/schema-2.0 status; ROADMAP mojibake. | Planned (C). |
| P2-6 | `ARCHITECTURE.md` references obsolete paths (`cli.py`, `aihwbench/experiments`, `aihwbench/hardware/`). | Planned (C). |
| P2-7 | CI coverage gate 55%. | Planned (C): measure then raise gradually with branches + critical-module floors. |
| P2-8 | mypy globally weakened despite `py.typed`. | Planned (C): strict per-module. |
| P2-9 | `npm ci --no-audit`; no dependency review. | Planned (C). |
| P2-10 | No artifact provenance/attestation beyond fingerprint. | Planned (C). |

## P3 — Observation-level findings

- No fabricated benchmark numbers found anywhere; published results keep
  nulls honest (verified by parsing and re-validating every published result).
- `configs/suites/` declarative and validated.
- `docs/enterprise/overview.md` correctly marked "planned" — no overclaim.
- License hygiene sound (Apache-2.0; contributor copyright retained).

## Re-verified web of checks run on the remediation branch

- `ruff check aihwbench tests scripts` — clean.
- `ruff format --check aihwbench tests scripts` — clean.
- `mypy aihwbench` — clean.
- `pytest` (full suite, plugin autoload disabled) — pass.
- `python scripts/generate_frontend_data.py` — succeeds; tracked
  `web/public/data` diff = none (fail-closed change behavior-preserving).
- `python scripts/verify_action_pins.py` — 16 pinned actions, 0 invalid.
- Every published result re-validates against the semantic schema.
  any unreadable member; `generate_frontend_data.py` validates schema +
  privacy on every file and aborts (exit 2) on any problem — CI/publishing
  paths now cannot silently publish a subset. Lenient exploration stays
  available (default and `--tolerant`). Tests:
  `tests/test_fail_closed.py`.

---

### P0-11. CI gates record failures but never fail (fail-open)

**Evidence (`d1503a0`).** The reusable `benchmark-validation.yml` workflow
wrote `verdict="fail"` into `$GITHUB_OUTPUT` but never exited non-zero;
`aihwbench quality` and `aihwbench anomalies` ran under `|| true`; the
regression candidate was `ls | head -1` (arbitrary). `release.yml` could
"generate" an SBOM by printing `SBOM generation skipped (tool unavailable)`
and still succeed, while ROADMAP claims SBOMs are part of the release
flow.

**Fix — commit `0b520a5`.**
- `benchmark-validation.yml` aggregates a fail-closed verdict → the job
  exits 1 when `fail-on-validation-failure` (default true) and any result
  fails schema/privacy; quality crashes also flip the verdict; anomaly/quality
  failures are surfaced (never `|| true`); regression candidate selection is
  deterministic (newest `timestamp`), and an optional `fail-on-regression`
  gate exists.
- `release.yml` SBOM generation is mandatory: `set -e`, no swallowed
  `echo`, and a **Verify SBOM** step asserts a real CycloneDX document
  exists before release.

**Tests.** `tests/test_workflow_gates.py` (fail-closed step present and
conditioned on the verdict, no `|| true` in the workflow, deterministic
candidate selector, SBOM mandatory + verified, all workflows parse).
**Evidence (`d1503a0`).** `verify_bundle` listed `extra_members` (unmanifested
ZIP members) but `"valid": not mismatches and not missing` — so an injected
unchecksummed member still verified as valid. Manifest format had no grammar
check (duplicate entries, malformed lines), and no archive safety caps
(member count / uncompressed size / compression ratio) existed → zip-bomb
surface.

**Fix — commit `339acb5`.** Verification is fail-closed by default:
any member not listed in `MANIFEST.sha256` makes the bundle invalid
(`allow_extra_members=True` is an explicit opt-out for tolerating
compat-wrapped archives). Manifest lines are strictly validated; duplicate
entries are rejected; member-count, total-uncompressed-size and
compression-ratio caps are enforced.

**Tests.** `tests/test_bundles_strict.py` (injected member → invalid,
manifest duplicate → invalid, oversized archive → invalid, high-ratio →
invalid, valid round-trip still passes, opt-in tolerance works).

---

### P0-6. Duplicated privacy scanners that echo secrets

**Evidence (`d1503a0`).** `sanitize.py` and `quality.py` ran *different*
regex sets (email/serial only in quality; Windows-user/home-path only in
sanitize) with different semantics and outputs. `sanitize.scan_object`
stringified values instead of recursing structurally, and findings
**echoed full matched values** (`findings.append(f"{label}: {match.group(0)!r}")`).

**Fix — commit `fb4545d`.** One canonical recursive structured scanner in
`sanitize.py` (dict/list recursion with JSON-path context; filename
exclusion; MAC/IPv4/IPv6/SSN/token/home-path/username/serial patterns);
findings are **redacted** (pattern label + JSON path, never the matched
value); `quality.py` delegates to it, producing the same pattern-id list
(`privacy_hits`) as before so downstream contracts hold.

**Tests.** `tests/test_privacy_scan.py` (redaction assertion: raw secret
never appears in findings; structural recursion; Windows/Linux path
patterns; token/credential detection; MAC detection).