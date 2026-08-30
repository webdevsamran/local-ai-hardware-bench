# AIHWBench Remediation Plan

Status of the audit remediation, keyed to `docs/audit/REPOSITORY_AUDIT.md`.
Implementation order follows the task's phases with small reviewable
commits. Every item links its evidence and fix commit / test.

Legend: ✅ done · 🔜 planned · ⚠️ partial · ❌ not started

## Phase A — P0 correctness / data integrity / security ✅

| Item | Fix commit | Tests | Status |
| --- | --- | --- | --- |
| A1 Open-loop loadgen preserves scheduled submit time | `ac60da6` | `test_loadgen_timing.py` | ✅ |
| A2 Gamma arrivals rate-independent of shape | `ac60da6` | `test_loadgen_timing.py` | ✅ |
| A3 Telemetry platform-safe + scope/source/device provenance | `ac60da6` | `test_telemetry_scope.py` | ✅ |
| A4 Bundle verification fail-closed (extras/manifest/safety caps) | `339acb5` | `test_bundles_strict.py` | ✅ |
| A5 Unified recursive privacy scanner, redacted findings | `fb4545d` | `test_privacy_scan.py` | ✅ |
| A6 Canonical trust lifecycle + legacy mapping | `49e1788` | `test_trust_lifecycle.py` | ✅ |
| A7 llama.cpp usage-only tokens + ephemeral port | `1f3599e` | `test_backend_contracts.py` | ✅ |
| A8 LM Studio metric-source separation | `1f3599e` | `test_backend_contracts.py` | ✅ |
| A9 ORT/OpenVINO feed all inputs + model checksum | `1f3599e` | `test_backend_contracts.py` | ✅ |
| A10 Canonical metric IDs + alias-tolerant readers | `0a6e6e5` | `test_metric_aliases.py` | ✅ |
| A11 Fail-closed publishing/dataset pipelines | `4583444` | `test_fail_closed.py` | ✅ |
| A12 CI fail-closed gates + mandatory verified SBOM | `0b520a5` | `test_workflow_gates.py` | ✅ |

## Phase B — Architecture consolidation 🔜

| Item | Notes |
| --- | --- |
| B1 Authoritative version source; explicit reader/writer versions | P1-1 |
| B2 Versioned formal schemas (`result-1.0`, `result-2.0`) + contract tests | P1-2 |
| B3 Pure/idempotent migrations; corrected migrator names; deep copy | P1-3 |
| B4 Domain MISSING/null/INVALID tri-state; strict/lenient modes | P1-4 |
| B5 Anomaly detection cohorts by comparability profile; median/MAD; min-N | P1-5 |
| B6 Fingerprint v2: experiment identity vs artifact hash; protocol_version | P1-6 |
| B7 Capacity methodology: one defined, tested rule | P1-7 |
| B8 Comparison profiles (hardware/runtime/config/regression/exploratory) | P1-8 |
| B9 Frontend hardware fingerprint v2 (normalized topology/RAM) | P1-9 |
| B10 Canonical dataset-generation library (CLI/scripts/frontend one path) | — |
| B11 Plugin capability contract (detection-only ≠ benchmark-capable) | — |

## Phase C — Test / CI / release hardening 🔜

| Item | Notes |
| --- | --- |
| C1 Coverage gate raised gradually (branch coverage + critical-module floors) | P2-7 |
| C2 mypy strict per-module (drop global weakening) | P2-8 |
| C3 npm dependency review/audit policy (offline-independent) | P2-9 |
| C4 SBOM verified (done in A12); add attestation/signing roadmap | P2-10 |
| C5 Docs-truth reconciliation: ARCHITECTURE, ROADMAP, SECURITY, README | P2-5, P2-6 |
| C6 Property/fuzz/contract tests (Hypothesis) for stats/fingerprint/etc. | — |

## Phase D — Frontend quality/scalability 🔜

| Item | Notes |
| --- | --- |
| D1 Fix double `index.json` fetch; lazy loads; pagination abstraction | P2-1 |
| D2 Generated TS contracts + runtime validation | P2-2 |
| D3 `*.tsbuildinfo` ignore + untrack | P2-3 |
| D4 HashRouter for static hosting deep links (ADR-0006) | P2-4 |
| D5 Playwright E2E/a11y; loading/error/empty/offline states | — |
| D6 Uncertainty/provenance/trust UI; valid comparison cohorts | — |

## Phase E — Optional open-source server foundations 🔜 (design only, explicit)

- REST `/v1` API + PostgreSQL metadata + S3-compatible object storage
  interfaces, designed to be **cleanly optional**; the community CLI keeps
  zero server dependency. See `docs/enterprise/overview.md` and
  ADR-0007. No server code lands in the core or in `docs/enterprise`
  until the design is reviewed.

## Phase F — Enterprise/private layer ❌ (design with counsel)

- Multi-tenancy, SSO/RBAC/audit, policies, entitlements, air-gap ops,
  licensing boundary (ADR-0008, `LICENSING.md` placeholder). Far-term.

## Open items turned into the PR description

1. Phase B PRs (schemas/migrations/comparability/fingerprint).
2. Phase C: coverage/myypy/security audits.
3. Phase D: frontend data layer + routing.
4. Next-10 issue queue (see PR description).

## Re-verification gate (run before merging this branch)

- [x] `pytest` full suite passes (plugin autoload disabled).
- [x] `ruff check` + `ruff format --check` clean.
- [x] `mypy aihwbench` clean.
- [x] `scripts/generate_frontend_data.py` succeeds; generated data drift = 0.
- [x] `scripts/verify_action_pins.py` — 0 invalid.
- [x] Published results re-validate; dataset exports deterministic.