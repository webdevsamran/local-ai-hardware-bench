# AIHWBench Enterprise — Overview (Planned / Future)

> **Status: planned.** Nothing described on this page exists as a
> product today. This document describes the intended architecture so
> the open-source core can prepare clean interfaces. No proprietary
> code lives in this repository.

## Intended architecture

```
AIHWBench Core/Agent (open source, this repo)
  -> Result Artifact (schema-validated JSON, fingerprinted)
  -> Enterprise Collector        [planned]
  -> Private Result Store        [planned]
  -> Regression/Policy Engine    [planned]
  -> API / Dashboard             [planned]
  -> SSO/SAML, RBAC, Audit Logs  [planned]
```

## What the open core already provides

The Community edition is deliberately useful for enterprise workflows
today:

- Machine-readable JSON output and stable CLI exit codes.
- Fully offline operation; no cloud dependency.
- Deterministic suite profiles (`configs/suites/`).
- Result fingerprints for duplicate/regression detection.
- Schema validation suitable as a CI gate.

## Planned capabilities (not implemented)

| Capability | Status |
| --- | --- |
| Fleet benchmarking & centralized orchestration | planned |
| Private result storage adapters | planned |
| Organization/team management | planned |
| Dashboards & regression monitoring | planned |
| CI performance gates with baseline policies | partially available via `compare` exit codes |
| SSO/SAML, RBAC, audit logs | planned |
| Signed results / attestation interfaces | interface documented; crypto not implemented |
| Air-gapped deployment support | already possible offline; packaging planned |
| SLA/support | planned |

## Design principles

1. **No artificial lock-in.** Basic benchmarking stays free and open.
   Enterprise adds scale and governance, not paywalled basics.
2. **Open artifacts.** Results remain standard JSON readable by anyone.
3. **Air-gap friendly.** The core never phones home.

## Feedback

If your organization has requirements (fleet scale, compliance,
retention), open a discussion — requirements shape the roadmap.