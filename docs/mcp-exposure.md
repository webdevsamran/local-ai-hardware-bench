# Should aihwbench expose an MCP server?

**Verdict: split. Yes for reading and comparing results; no for running
benchmarks.** The dividing line is duration and hardware, not safety.

This is an assessment, not a feature. Nothing here ships today.

## Why the read side fits

*"Which runtime is faster on my hardware for this model?"* is a question agents
are asked and answer from memory, which is exactly how wrong benchmark numbers
propagate. This project holds real measurements with the provenance attached —
CPU, GPU, driver, RAM, runtime version, model checksum, seed, iteration counts
— and, more usefully, holds a classifier that refuses unsafe comparisons.

That refusal is the interesting part to expose. An agent asking "compare these
two results" should sometimes get back *"you may not, and here is why"*, and
`comparability.py` already produces that answer with reasons attached rather
than a number with a caveat buried in prose.

| Tool | Answers |
|---|---|
| `compare` | Are these two results comparable, and if so how do they differ? |
| `analyze` | Summarise a result set |
| `score` / `repro-score` | How reproducible is this result? |
| `validate` / `verify-bundle` | Is this result document well-formed and intact? |
| `runtimes` | Which runtimes are detected on this machine? |
| `system-info` | What hardware is this? |
| `doctor` | Is this machine set up to benchmark meaningfully? |

## Why the run side does not fit

`benchmark`, `run`, `sweep`, `capacity` and `tune` all take minutes, saturate
the machine, and produce numbers whose validity depends on the machine being
otherwise idle. Three consequences:

1. **A tool call that takes four minutes is not a tool call.** MCP has no good
   answer for this beyond a job handle, at which point the protocol is doing
   less work than a shell.
2. **Concurrent invocation invalidates the measurement.** Two agents calling
   `benchmark` at once produce two wrong numbers, and nothing in the result
   would say so. The load generator assumes it owns the machine.
3. **The numbers would carry this project's provenance.** A result produced
   under unknown load, published with a full hardware manifest, is worse than
   no result — it looks trustworthy.

The read/write split here is not about danger. Running a benchmark harms
nothing. It is about whether the number that comes out means anything, which
is the only thing this project sells.

## What has to be true first

1. **Comparability must be surfaced, not summarised.** The tool result has to
   carry the classification (`STRICTLY_COMPARABLE`, `CONDITIONALLY_COMPARABLE`,
   `NOT_COMPARABLE`) and its reasons as structured fields. A model handed a
   number and a paragraph will report the number.
2. **Result path confinement**, as in the sibling projects.
3. **Zero dependencies is a real constraint here.** This project deliberately
   ships without runtime dependencies; an MCP server means a protocol library.
   It belongs behind an optional extra, not in the core.
