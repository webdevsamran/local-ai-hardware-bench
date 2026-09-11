# Private result storage — adapter interface (Planned / Future)

> **Status: planned.** No adapter exists in this repository and none is
> shipped. This page specifies the boundary so the open core can be built
> against a real contract rather than a guess, and so that anyone writing a
> private store — a company keeping results off the public dataset, a lab with
> an internal archive — has something to implement.

## What problem this is for

A team benchmarking hardware before purchase produces results they will not
publish: unreleased silicon, a vendor evaluation under NDA, a competitor's
product. The core already works entirely offline and writes plain JSON, so
today they use a directory. That is fine until there are ten machines and
someone asks which results are current.

The boundary below is the smallest one that lets a private store do that job
without the core knowing anything about it.

## The artifact is the interface

An adapter stores and retrieves **result documents** — the same schema-validated
JSON the CLI already writes. Not a database row, not a projection.

This is the load-bearing decision. A store that keeps its own shape has to be
migrated whenever the schema moves, and worse, becomes the thing people query
instead of the artifact. Results that outlive the tool that stored them are the
point of the format.

What the core guarantees about every artifact:

| Property | Provided by | Meaning for an adapter |
|---|---|---|
| Schema-valid | `aihwbench validate --formal` | Reject anything that fails; do not repair |
| Content fingerprint | `fingerprint.result_fingerprint` | Stable id for dedupe; see below |
| Integrity-checkable | `aihwbench bundle` / `verify_bundle` | SHA-256 per member |
| Comparison metadata complete | schema 2.1 required fields | Every field the classifier reads is present |

## Required operations

```
put(result: dict) -> str          # returns the fingerprint; idempotent
get(fingerprint: str) -> dict | None
list(filter: dict) -> Iterable[str]
delete(fingerprint: str, reason: str) -> None
```

Four, deliberately. Anything richer — aggregation, ranking, comparison — belongs
in the core, where it is tested and where the comparison-safety rules live. An
adapter that ranks results is a second implementation of the leaderboard, and
it will disagree with the first.

### `put` is idempotent, keyed by fingerprint

`result_fingerprint` hashes the fields that define *what was measured*, not when
it was written. The same benchmark stored twice is one record. This is not an
optimisation: fleet collection retries, and a store that appends on retry
reports a machine as twice as productive as it is.

### `delete` takes a reason

Not a nicety. The public dataset already has an
[invalidation record](../disputes.md) rather than deletion, because a result
that silently disappears is indistinguishable from one that was never taken. A
private store needs the same property for the same reason — more so, since
nobody outside can notice.

## What must not cross the boundary

- **No network calls from the core.** The core never phones home; an adapter is
  something a caller invokes, not something the core discovers or contacts.
- **No proprietary code in this repository.** Adapters live in the caller's
  own package and are registered through the existing
  [plugin entry points](../guides/plugin-api.md).
- **No credentials in a result.** The privacy scanner
  (`aihwbench scan`) already refuses to publish documents carrying
  identifiers; an adapter must not add any on the way in.
- **No adapter-specific fields in the artifact.** If a store needs an index,
  it keeps it beside the artifact, not inside it. A result that only one store
  can read is not a result.

## What the open core still owes this

Honest gaps, listed so the spec is not mistaken for a plan that is already met:

- `put`/`get` have no reference implementation, not even a filesystem one.
  Writing that would test whether this interface survives contact.
- There is no registered entry-point group for storage adapters. Backends,
  exporters, evaluators and workloads have one; storage does not.
- Signed results are documented as an interface and the crypto is not
  implemented, so an adapter cannot yet verify authorship — only integrity.

## Why it is specified before it is built

An interface written after two implementations exist is a description of
whatever those two happened to do. The point of writing it now is that the
constraints above — artifact in, fingerprint as identity, no ranking in the
store — are decisions, and they are cheaper to make here than to retrofit.
