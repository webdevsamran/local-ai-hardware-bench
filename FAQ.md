# Frequently Asked Questions

## General

**Is AIHWBench free? Can I use it commercially?**
Yes. The core is Apache-2.0 — free for personal and commercial use.
Future Enterprise/Cloud offerings will add scale and governance, never
artificially lock basic benchmarking.

**Does it send my data anywhere?**
No. Everything runs locally and works offline. Results are published
only when you explicitly submit them, after privacy scanning.

**Is my hardware supported?**
Run `aihwbench doctor`. Runtimes without the required hardware report
`HARDWARE_REQUIRED` honestly rather than pretending.

## Benchmarks

**Why can't I compare two results?**
The comparison classifier refuses comparisons when model identity,
workload parameters, or protocol differ. This prevents misleading
"winner" claims. See [methodology](docs/methodology.md).

**Why are some metrics null?**
Because the runtime didn't expose them. AIHWBench never estimates
unavailable data.

**What does "Tested" mean?**
Real execution on that hardware produced a validated result. Anything
else is labeled NOT_INSTALLED / HARDWARE_REQUIRED / CONFIGURATION_REQUIRED.

**What do trust states mean?**
The canonical values are lowercase and defined in `aihwbench/trust.py`:

- `verified` — executed on a maintainer-controlled reference machine
- `community_validated` — independently reproduced by a community member
- `unreviewed` — submitted, not yet reproduced (the default for new results)
- `flagged` — statistically anomalous; queued for human review, never auto-rejected
- `invalidated` — withdrawn with a recorded reason; history is preserved
- `superseded` — replaced by a referenced newer result

`UNVERIFIED` appears in older code as a deprecated alias of `unreviewed`; new
code should use `unreviewed`.

## Contributing

**How do I add a runtime backend?**
See the [Plugin API guide](docs/guides/plugin-api.md) and
[backend docs](docs/backends/overview.md). Third-party backends ship as
separate packages via entry points.

**Do I have to sign a CLA?**
No. Contributions remain Apache-2.0; you keep copyright (see
[GOVERNANCE.md](GOVERNANCE.md)).