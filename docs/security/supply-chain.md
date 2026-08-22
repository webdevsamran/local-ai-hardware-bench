# Supply Chain

## Current measures

- **Zero runtime dependencies** — the CLI installs nothing beyond Python itself
- **Pinned Actions** — every GitHub Action is pinned to an immutable commit SHA
- **Least privilege** — workflows default to `contents: read`; write scopes granted per-job only
- **Dependabot** — weekly updates for GitHub Actions and pip dev dependencies
- **CodeQL** — security-extended static analysis on every PR and weekly
- **Release artifacts** — sdist + wheel + SHA256SUMS + CycloneDX SBOM attached to GitHub Releases

## Verification

```bash
sha256sum -c SHA256SUMS.txt   # after downloading release artifacts
```

## Planned

- Artifact provenance attestation (tracked in issues #3/#4)
- PyPI Trusted Publishing (only when actually configured)
- OpenSSF Scorecard badge (once the project has release history)

## Reporting vulnerabilities

See [SECURITY.md](../../SECURITY.md) — do not open public issues for
security reports.