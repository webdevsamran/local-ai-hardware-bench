# Result Schema 2.0 (Proposal)

**Status: PARTLY SHIPPED — read this as a design note, not as status.**

Schema 2.0 is implemented and readable forever, but it is no longer what the
writer emits: `aihwbench/versions.py` sets `CURRENT_SCHEMA_VERSION = "2.1"`,
which adds no fields and *requires* the ones the comparison-safety classifier
reads (see `schemas/result-2.1.schema.json`). Under 2.0 an empty document
validated, and the classifier read two absent fields as agreement.
(Historically, `aihwbench/versions.py` set `CURRENT_SCHEMA_VERSION = "2.0"`;
`schemas/result-2.0.schema.json` ships and is enforced by
`aihwbench validate --formal`). Every result committed to
`results/published/` so far predates it and carries `schema_version` 1.0,
which the reader migrates forward.

The candidate changes listed below are a mix: some shipped with 2.0, and
others — promoting the fingerprint to required, a `gpus[]` array, an ITL
distribution, suite provenance, backend-plugin identity — have not. Treat
each as a proposal to check against the schema file, never as a statement
of what the code does.

## Motivation

Schema 1.0 has proven sufficient for published results, but community
submissions and enterprise use surfaced gaps:

1. **Multi-GPU / heterogeneous devices** — `hardware.gpu` is single-valued
2. **Distributional ITL** — only mean ITL is derivable today; per-token
   timestamps would enable p50/p99 ITL
3. **Suite provenance** — results from suite profiles should record the
   profile name + version explicitly
4. **Backend plugin identity** — third-party backends need a namespace

## Candidate changes

| Area | Change | Back-compat |
|---|---|---|
| hardware | `gpus: []` array alongside legacy `gpu` object | additive |
| metrics | `itl: {p50, p90, p99, mean, source}` where source ∈ {measured, derived} | additive |
| workload | `suite: {name, version}` optional block | additive |
| runtime | `backend_plugin: {name, api_version, package}` for entry-point plugins | additive |
| integrity | `fingerprint` promoted to required field | breaking → migration reader |
| telemetry | `samples_path` reference to sidecar sample files | additive |

## Migration policy

- Validators will read both 1.x and 2.x (`schema_version` discriminates)
- Published 1.0 results are never rewritten; new fields are added on
  re-validation only when re-measured
- A migration tool will be provided before any 2.0 release

## Non-goals

- No removal of existing fields without a full deprecation cycle
- No vendor-specific extensions in the core schema (use `x_` prefixed
  extension objects, ignored by strict validators)