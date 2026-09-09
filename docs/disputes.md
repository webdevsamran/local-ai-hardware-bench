# Disputed and challenged results

The moment a leaderboard matters to anyone, someone will want a result changed
— removed, re-ranked, or re-labelled. That pressure is normal and it is not
always illegitimate: results really do turn out to be wrong. What matters is
that the process is written down *before* it is needed, so a decision can be
checked against a rule instead of a mood.

This page is that process. It covers results already in the public dataset.
Submission and review of new results is in
[CONTRIBUTING.md](../CONTRIBUTING.md).

## What you can dispute

Anything factual about a published result:

- the measurement is wrong (misconfigured run, wrong model, wrong device)
- the environment is misreported (driver version, quantization, power profile)
- it duplicates another run and is being counted twice
- it is being compared with something the
  [comparability rubric](comparability-rubric.md) says it should not be

You cannot dispute a result **for being unflattering**. "This makes our
hardware look bad" is not a defect. If the run was misconfigured, say which
setting was wrong and what it should have been; that is a claim anyone can
check, and it is welcome.

## How to raise one

Open an issue titled `dispute: <run_id>` containing:

1. the `run_id`, from `results/published/`
2. what specifically is wrong — a field, a number, a comparison
3. the evidence: a corrected run, upstream documentation, or a reproduction
4. your relationship to the hardware or runtime involved, if any

Point 4 is a disclosure, not a disqualification. A vendor engineer who spots
a misconfiguration is often the person best placed to spot it. Undisclosed,
the same correction is much harder to trust.

## What happens next

| Stage | What it means | Who |
|---|---|---|
| **Raised** | An issue exists. The result stays visible and unchanged. | Anyone |
| **Under review** | Trust state moves to `flagged`; the result is excluded from leaderboards while the question is open. | Maintainer |
| **Resolved — no change** | The result stands. The reasoning is written in the issue. | Maintainer |
| **Resolved — invalidated** | The result was wrong. It is marked `invalidated` with a reason and **kept**. | Maintainer |
| **Resolved — superseded** | A corrected re-run replaces it. Both remain, linked by `replacement_run_id`. | Maintainer |

Two things never happen:

- **Nothing is deleted.** `aihwbench invalidate` wraps a result in an
  invalidation record that preserves the original verbatim. A dataset that
  quietly loses its mistakes cannot be audited, and the mistakes are often the
  most informative part of it.
- **No result is silently edited.** A number changes by superseding the run,
  never by rewriting it in place.

## Automated flags are not accusations

`aihwbench anomalies` flags results that deviate from their cohort, and
`aihwbench quality` reports schema, privacy and variance checks. Both produce
**review requests**. A flag says "a human should look at this", never "this is
fraudulent" — an unusual number is the expected outcome of unusual hardware,
which is the entire point of the dataset.

A flagged result is excluded from leaderboards pending review, which is a
statement about confidence, not about the submitter.

## Conflicts of interest

The lead maintainer decides disputes, per
[GOVERNANCE.md](../GOVERNANCE.md). Where the maintainer has an interest in the
outcome — their own hardware, their own result, a sponsored machine — that is
stated in the issue and a second reviewer is sought before the trust state
changes.

Vendor-supplied results and sponsored testing are labelled as such wherever
they appear. Neutrality is the product; a dispute process that could be
influenced quietly would remove the reason to trust any of it.

## If you disagree with the outcome

Say so in the issue. Decisions are written down precisely so they can be
argued with, and reversed if the argument is good. If a decision is reversed,
that is recorded too.
