# Result Schema

This directory contains the formal JSON Schema for AIHWBench benchmark result
documents.

| File | Description |
| --- | --- |
| `result-1.0.schema.json` | JSON Schema (draft 2020-12) for schema-version 1.0 result documents |
| `result-2.0.schema.json` | JSON Schema (draft 2020-12) for schema-version 2.0 result documents — **what the current writer emits** |

Both files are loaded by `aihwbench/formal_schema.py`, which selects one from
the document's own `schema_version`. A previously shipped
`result_schema.schema.json` was a byte-identical copy of the 1.0 file that no
code path loaded, and it carried the `$id` that `result-1.0.schema.json` was
also claiming; it has been removed and each file's `$id` now matches its own
filename.

## Schema versioning

- The schema version is declared inside every result document as
  `schema_version`.
- Backward-compatible changes (new optional fields, relaxed constraints)
  keep the same major schema version and are documented in the
  `CHANGELOG.md`.
- Breaking changes (removing fields, tightening constraints that invalidate
  existing published results) require a new major schema version and a
  migration/read path for previously published results.

## Validation

The authoritative runtime validator is `aihwbench/schemas.py`
(`validate_result`). It performs type checks, semantic range checks,
timestamp/run-id format checks, and nested object validation without any
third-party dependencies.

The formal JSON Schema file is the declarative reference and is used by
CI and external tooling where available.

## Metrics

A metric that could not be measured MUST be `null`, never an estimate.
Percent utilisation metrics are range-checked 0–100. All timing and
bandwidth metrics must be non-negative.