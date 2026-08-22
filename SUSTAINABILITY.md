# Project Sustainability

How AIHWBench funds long-term maintenance **without compromising the
open-source core**.

## The flywheel

```
OPEN STANDARD → ADOPTION → CONTRIBUTORS → MORE HARDWARE RESULTS
→ TRUSTED DATASET → VENDOR/ENTERPRISE ADOPTION → COMMERCIAL SERVICES
→ FUNDED MAINTENANCE → BETTER OPEN STANDARD
```

## What stays free, forever

The Apache-2.0 core will never be crippled to sell a product:

- CLI, detection, benchmarking, validation, comparison, export
- All suite profiles and schemas
- Local/offline operation
- The public dataset and leaderboard foundations

Companies may run the full core internally at no cost. We monetize
*scale and governance*, not basic benchmarking.

## Planned revenue paths

| Path | Status | Notes |
| --- | --- | --- |
| AIHWBench Enterprise | Planned | Fleet orchestration, private storage, regression policies, RBAC/SSO/audit |
| AIHWBench Cloud | Planned | Hosted dashboards over public/private results |
| AIHWBench Certified | Planned | Hardware/runtime verification program (defined process required first) |
| AIHWBench Labs | Planned | Independent testing/vendor validation reports |
| Sponsored engineering | Open | Vendor-funded backend work, disclosed publicly |
| Training / workshops | Open | Benchmark methodology education |
| GitHub Sponsors | Not configured | Will appear in FUNDING.yml only when real |

Nothing in this table exists today beyond the open-source core.
Each offering launches only with working software or a defined,
evidence-based process — see [TRADEMARKS.md](TRADEMARKS.md) for naming
rules and [docs/enterprise/overview.md](docs/enterprise/overview.md)
for the planned enterprise architecture.

## Sponsorship disclosure rules

- Any vendor-funded work is disclosed in the PR and release notes
- Evaluation hardware is listed on [platforms/](platforms/) with its source
- No vendor gets editorial control over published results
- Negative results are published like any other result

## For maintainers

Time-funded priorities: correctness > coverage > features. The dataset's
value depends entirely on trust; every shortcut that saves time but costs
credibility is a net loss.