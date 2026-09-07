# Release process

What `.github/workflows/release.yml` actually does. If this page and the
workflow disagree, the workflow is authoritative and this page is the bug.

## Trigger

A pushed tag matching `v*.*.*`. Nothing else — there is no manual publish path.

```bash
# Versions must agree before tagging
grep '^version' pyproject.toml      # source of truth
grep '^version:' CITATION.cff
head -20 CHANGELOG.md               # promote [Unreleased] to the new version
aihwbench --version

git tag -a v0.2.0 -m "v0.2.0"
git push origin v0.2.0
```

## What the workflow produces

| Job | Output |
| --- | --- |
| `Build, checksum, SBOM` | sdist + wheel, `twine check`, `SHA256SUMS`, a CycloneDX SBOM that is **verified** (bomFormat and component count are asserted, not assumed), and SLSA build provenance via `actions/attest-build-provenance` |
| `GitHub Release` | Creates the release from the tag with generated notes and attaches every artifact |
| `Publish to PyPI` | Uploads via Trusted Publishing — **guarded, see below** |

## The PyPI step is deliberately guarded

Publishing uses OIDC Trusted Publishing rather than a stored API token, which
requires a Trusted Publisher registered for this project on pypi.org. That
cannot be created from this repository, and until it exists an unconditional
upload step would fail a tagged release *after* the build, SBOM, checksums and
GitHub Release had all succeeded — turning a good release into a red one for a
reason unrelated to the code.

So the job skips with a notice unless the repository variable
`PUBLISH_ENABLED` is `true`.

To enable it, once:

1. On pypi.org → **Your projects → Publishing**, add a pending publisher:
   - Owner: `webdevsamran`
   - Repository: `local-ai-hardware-bench`
   - Workflow: `release.yml`
   - Environment: `pypi`
2. In this repository, set the variable:
   ```bash
   gh variable set PUBLISH_ENABLED --body true -R webdevsamran/local-ai-hardware-bench
   ```

## After a release

A green workflow is not evidence the package is usable. Confirm it installs by
its real name from a clean environment:

```bash
python -m venv /tmp/verify && /tmp/verify/bin/pip install aihwbench
/tmp/verify/bin/aihwbench --version
```
