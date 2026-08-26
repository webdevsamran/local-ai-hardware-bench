# Privacy

## What leaves your machine

Nothing automatically. AIHWBench is local-first and offline-capable.
Results are written to local files; publication happens only when you
explicitly submit them.

## Sanitization

Before any result can be published it must pass the privacy scanner
(`aihwbench/sanitize.py`), which fails closed on:

- MAC addresses
- IPv4/IPv6 addresses
- Social security numbers
- API tokens / bearer credentials
- Home directory paths (`C:\Users\<name>`, `/home/<name>`)
- Windows usernames
- Serial-number patterns

Detection itself never records these values; hostnames are not collected.

## CI enforcement

Every PR touching results runs the scanner in CI
(`Result pipeline` job). A submission containing private data cannot merge.

## Reporting a privacy issue

See [SECURITY.md](../../SECURITY.md).