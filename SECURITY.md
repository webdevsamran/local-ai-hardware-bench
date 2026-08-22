# Security Policy

## Data hygiene (applies to all contributions)

Benchmark results are public artifacts. Never include:

- API keys, tokens, credentials
- Usernames or home-directory paths
- MAC addresses or public IPs
- Serial numbers or confidential hardware IDs
- NDA-covered information

Detection output produced by `aihwbench` is sanitized by design, and a
fail-closed privacy scanner (`benchmark/sanitize.py`) checks published
artifacts for accidental exposure. You remain responsible for anything
you paste into issues or results files.

## Reporting vulnerabilities

Report security issues privately via GitHub Security Advisories
("Report a vulnerability" on the repository) rather than public issues.
You will receive an acknowledgment within 7 days.

Scope: the `aihwbench` CLI, detection/telemetry code, and CI workflows.
Out of scope: vulnerabilities in upstream runtimes (Ollama, llama.cpp,
ONNX Runtime, ...) — please report those to the respective projects; we are
happy to help reproduce.

## Supported versions

| Version | Supported |
| --- | --- |
| 0.1.x | Yes |

## CI & supply chain

- GitHub Actions are pinned to **immutable commit SHAs** (not mutable tags).
- Workflows use minimal permissions (`contents: read`).
- Dependabot monitors both GitHub Actions and pip dependencies (weekly).
- No secrets are required to build or test the project.
- Model downloads never happen in CI.
- Release artifacts should ship with checksums; SBOM generation is on the
  roadmap (see ROADMAP.md).

## Secret scanning

Enable GitHub secret scanning and push protection on your fork. Never
commit tokens; if one leaks, revoke it immediately before history
cleanup.