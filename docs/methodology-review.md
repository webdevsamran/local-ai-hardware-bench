# Methodology review — request for external reviewers

**Status: open. Tracked in [#21](https://github.com/webdevsamran/local-ai-hardware-bench/issues/21)
and ROADMAP Track 8. This page is the packet a reviewer needs; it is not a
record of a completed review.**

This project publishes hardware benchmark numbers and asks people to trust
them. That trust should not rest on the maintainer's own say-so, so before
v1.0 the methodology and the comparison-safety classifier need review by
people who did not write them — runtime maintainers, hardware vendors, and
researchers who benchmark for a living.

## What to review

| Artifact | What it is |
| --- | --- |
| [`docs/methodology.md`](methodology.md) | Controlled variables, measurement definitions, statistical policy, and the known-limitations section |
| [`aihwbench/comparability.py`](../aihwbench/comparability.py) | The classifier that decides whether two runs may be compared at all |
| [`docs/adr/`](adr/) | ADRs 0001-0008, recording why each of these decisions was made |
| [`results/published/`](../results/published) | Six real results, with the environment metadata a reviewer needs to judge whether the claims hold |

## The questions that actually need answering

Generic "does this look right?" feedback is hard to act on. These are the
decisions where being wrong would matter most, and where an outside opinion
changes what we do:

1. **Is the strict-comparability field set right?** Two runs are declared
   `STRICTLY_COMPARABLE` only when all twenty fields in `_STRICT` match —
   model name, checksum, format, quantization, revision, tokenizer; runtime
   name, backend, device; and workload type, prompt, max_tokens, temperature,
   seed, context length, batch size, concurrency, warmup runs, iterations.
   **Is anything in that list actually irrelevant, and — more importantly — is
   anything missing that would make two runs incomparable in practice?**

2. **Are the three conditional fields correctly placed?** Differing
   `power_profile`, `os_version` or `runtime.version` currently downgrades a
   comparison to `CONDITIONALLY_COMPARABLE` rather than rejecting it. A
   runtime version change can alter performance substantially. Is
   "conditional" the honest classification, or should it be `NOT_COMPARABLE`?

3. **Is the warmup and iteration policy defensible?** See the statistical
   policy section. Published results use 2 warmups and 5 iterations. Is that
   enough to be meaningful on the hardware you work with?

4. **Does anything in `docs/methodology.md` overstate what the numbers
   support?** The known-limitations section is meant to be exhaustive. What is
   missing from it?

5. **Performance-per-watt is workload-dependent** — tok/s/W for generative
   runtimes, inf/s/W for graph runtimes — and results now publish the unit
   alongside the value. Is presenting both in one leaderboard defensible at
   all, even labelled, or should they be separated entirely?

## How to respond

Comment on [#21](https://github.com/webdevsamran/local-ai-hardware-bench/issues/21),
or open a separate issue per finding if that is easier. Disagreement is more
useful than approval; a review that changes nothing is not evidence the
methodology is sound.

Every outcome will be recorded here — what was raised, what changed as a
result, and what was deliberately not changed and why — before the
methodology-review item on Track 8 is checked off.

## Review log

_No external review has been performed yet._
