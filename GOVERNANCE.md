# Governance

This project uses lightweight, pragmatic governance appropriate to its
current size. The priority is keeping the benchmark scientifically
honest while making contribution easy.

## Principles

1. **Scientific integrity over growth.** No fabricated hardware,
   metrics, or runtime support — ever.
2. **Vendor neutrality.** No vendor gets favorable treatment; results
   stand as measured.
3. **Low friction.** Small, focused PRs with clear tests are merged
   quickly.
4. **No copyright assignment.** Contributors retain copyright;
   contributions are licensed under Apache-2.0.

## Contributor ladder

| Level | How you get there | What it means |
| --- | --- | --- |
| **Contributor** | Open a PR or issue | Full participation; no special rights |
| **Recurring Contributor** | Several accepted contributions over time | Input on roadmap discussions; may be asked to review in their area |
| **Reviewer** | Sustained quality + demonstrated judgment | May approve PRs in their area of expertise (non-binding for results/schema) |
| **Maintainer** | Invited by existing maintainers by consensus | Merge rights; participates in decisions |

There is **no automatic promotion**. Promotion reflects sustained,
high-quality involvement and alignment with the honesty policy.

## Decision-making

- **Normal changes** (bug fixes, docs, new backends): reviewed and
  merged by maintainers/reviewers.
- **Results and methodology**: require lead-maintainer review. The
  compatibility matrix may only claim what was genuinely tested.
- **Schema changes**: require maintainer consensus; breaking schema
  changes need a migration path for published results.
- **Disputes**: resolved by discussion first; the lead maintainer makes
  the final call when consensus fails.

## Current maintainers

See [MAINTAINERS.md](MAINTAINERS.md).

## Changes to this document

Governance evolves with the project. Propose changes via PR; substantive
changes require maintainer consensus.