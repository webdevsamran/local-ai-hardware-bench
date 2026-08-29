"""Compact repository facts for the remaining issue batch -> _facts_out.txt."""
from __future__ import annotations

import pathlib
import re
import subprocess

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "scripts" / "_facts_out.txt"
lines: list[str] = []


def sig(rel: str, pat: str = r"^(def |class |    def )", limit: int = 300) -> None:
    f = ROOT / rel
    if not f.exists():
        lines.append(f"MISSING {rel}")
        return
    src = f.read_text(encoding="utf-8")
    src_lines = src.splitlines()
    lines.append(f"== {rel} ({len(src_lines)} lines) ==")
    for i, ln in enumerate(src_lines, 1):
        if re.match(pat, ln):
            lines.append(f"{i}: {ln}")


for rel in [
    "aihwbench/npu.py",
    "aihwbench/backends/capabilities.py",
    "aihwbench/formal_schema.py",
    "aihwbench/telemetry.py",
    "aihwbench/export.py",
    "aihwbench/backends/tensorrt.py",
    "aihwbench/backends/rocm.py",
    "aihwbench/backends/qnn.py",
    "aihwbench/backends/hailo.py",
    "tests/test_issue_batch2.py",
]:
    sig(rel)

pp = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
m = re.search(r"\[project\.optional-dependencies\][^\[]*", pp)
lines.append("== pyproject extras ==")
lines.append(m.group(0) if m else "NO EXTRAS BLOCK")

lines.append("== release.yml ==")
lines.append((ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8"))

t = ROOT / "tests/test_issue_batch2.py"
if t.exists():
    lines.append("== test_issue_batch2.py defs ==")
    for i, ln in enumerate(t.read_text(encoding="utf-8").splitlines(), 1):
        if re.match(r"^(def |class |import |from )", ln):
            lines.append(f"{i}: {ln}")

lines.append("== CITATION.cff exists: %s ==" % (ROOT / "CITATION.cff").exists())

g = subprocess.run(["git", "log", "--oneline", "-3"], cwd=ROOT, capture_output=True, text=True)
s = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True)
lines.append("== git log ==")
lines.append(g.stdout.strip())
lines.append("== git status ==")
lines.append(s.stdout.strip() or "(clean)")

OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"wrote {OUT} ({len(lines)} lines)")
