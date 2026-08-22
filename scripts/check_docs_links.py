"""Validate relative markdown links across README and docs/.

Stdlib-only; exits non-zero when a relative link target is missing.
External http(s) links are not fetched (kept offline-friendly).
"""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")

broken: list[str] = []
checked = 0

root_mds = sorted(p for p in ROOT.glob("*.md"))
targets = [ROOT / "README.md", *root_mds, *sorted((ROOT / "docs").rglob("*.md"))]
for md in targets:
    if not md.is_file():
        continue
    text = md.read_text(encoding="utf-8")
    for match in LINK_RE.finditer(text):
        target = match.group(1).strip()
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        checked += 1
        path_part = target.split("#")[0]
        if not path_part:
            continue  # pure anchor link within the same document
        resolved = (md.parent / path_part).resolve()
        if not resolved.exists():
            broken.append(f"{md.relative_to(ROOT)} -> {target}")

print(f"Checked {checked} relative link(s) in {len(targets)} markdown file(s).")
if broken:
    print("BROKEN LINKS:")
    for b in broken:
        print(f"  {b}")
    sys.exit(1)
print("All relative links resolve.")