"""Verify every pinned GitHub Action SHA in workflows resolves upstream.

Usage: python scripts/verify_action_pins.py
Fails (exit 1) if any `uses: owner/repo@<sha>` pin does not resolve to that
exact commit in the upstream action repository.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

WORKFLOWS = Path(__file__).resolve().parent.parent / ".github" / "workflows"
PIN_RE = re.compile(r"uses:\s*([\w.-]+/[\w.-]+)@([0-9a-f]{40})")


def main() -> int:
    pins: set[tuple[str, str, str]] = set()
    for path in sorted(WORKFLOWS.glob("*.yml")):
        for match in PIN_RE.finditer(path.read_text(encoding="utf-8")):
            pins.add((match.group(1), match.group(2), path.name))

    bad: list[tuple[str, str, str]] = []
    for repo, sha, fname in sorted(pins):
        proc = subprocess.run(
            ["gh", "api", f"repos/{repo}/commits/{sha}", "--jq", ".sha"],
            capture_output=True,
            text=True,
        )
        ok = proc.returncode == 0 and proc.stdout.strip() == sha
        print(f"{'OK ' if ok else 'BAD'} {repo}@{sha[:12]} ({fname})")
        if not ok:
            bad.append((repo, sha, fname))

    print()
    print(f"Checked {len(pins)} pinned action(s); {len(bad)} invalid.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
