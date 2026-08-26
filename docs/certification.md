# Certification Program — Future Definitions

> **Status: planned.** No hardware, runtime, or result is certified
> today. This document defines what the future marks WILL mean, so the
> process can be designed openly before anything carries a mark.

## Planned marks

| Mark | Intended meaning |
| --- | --- |
| **AIHWBench Tested** | A real benchmark executed on this hardware/runtime combination and a validated result exists in the public dataset. |
| **AIHWBench Verified** | "Tested" + independently reproduced by the project or a designated reviewer with matching methodology. |
| **AIHWBench Certified** | "Verified" + sustained-load/thermal validation across the required suites + revalidation on driver/runtime updates within a defined window. |

## Required evidence (all marks)

1. Schema-valid result documents from real executions (never estimates).
2. Full reproducibility block: prompt, sampling, seed, context length,
   warmups, iterations, power profile, exact command.
3. Model identity: name, format, quantization, checksum.
4. Runtime identity: name, version, backend/provider, device.
5. Privacy scan passed.

## Verification & revalidation

- Verification requires reproduction by someone other than the original
  submitter for `Verified` and above.
- Certifications expire when the runtime major version or GPU driver
  changes; revalidation re-runs the required suites.
- Conflicts of interest: vendor-submitted results are welcome but are
  labeled as such and never self-certified. Sponsored testing is
  disclosed in the report.

## What this program will NOT do

- Never guarantee favorable outcomes to sponsors.
- Never certify without completing the defined process.
- Never allow marketing claims beyond the actual mark earned.

Until this program launches, the only honest status labels are those in
[docs/compatibility-matrix.md](compatibility-matrix.md) and the trust
states defined in `aihwbench/trust.py`.