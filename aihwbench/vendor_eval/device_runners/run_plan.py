#!/usr/bin/env python3
"""Sequential on-device driver for vendor evaluation plans.

Runs one model per subprocess (clean device state between models), keeps the
Hugging Face cache within a disk budget by evicting previously benchmarked
repositories, and writes one JSON result + log per model.

Usage (on the evaluation machine)::

    python run_plan.py --plan plan.json --runner furiosa_llm_runner.py \
        --out-dir /workspace/vendor_eval/results --min-free-gb 24

``plan.json`` is ``{"models": [{"id": "...", "task": "generate|vlm|embed|score",
"notes": ["..."], "args": ["--extra", "flags"]}], "common_args": [...]}``.
Only list models the vendor has confirmed as in scope.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


def free_gb(path: str) -> float:
    return shutil.disk_usage(path).free / 2**30


def evict_until(min_free: float, keep: set[str], cache_path: str) -> list[str]:
    evicted: list[str] = []
    if free_gb(cache_path) >= min_free:
        return evicted
    try:
        from huggingface_hub import scan_cache_dir
    except ImportError:
        return evicted
    info = scan_cache_dir()
    repos = sorted(info.repos, key=lambda r: r.last_accessed)
    for repo in repos:
        if free_gb(cache_path) >= min_free:
            break
        if repo.repo_id in keep:
            continue
        revs = [r.commit_hash for r in repo.revisions]
        try:
            info.delete_revisions(*revs).execute()
            evicted.append(repo.repo_id)
            info = scan_cache_dir()
        except Exception as e:  # noqa: BLE001
            print(f"[evict] failed for {repo.repo_id}: {e!r}", flush=True)
    return evicted


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    ap.add_argument("--runner", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--min-free-gb", type=float, default=24.0)
    ap.add_argument("--only", default=None, help="comma list of model ids to run")
    ap.add_argument("--skip-existing", action="store_true")
    args = ap.parse_args()

    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    out_dir = Path(args.out_dir)
    (out_dir / "logs").mkdir(parents=True, exist_ok=True)
    cache_path = os.environ.get("HF_HOME", str(Path.home()))
    only = set(args.only.split(",")) if args.only else None
    status = []
    for entry in plan["models"]:
        mid = entry["id"]
        if only and mid not in only:
            continue
        slug = mid.split("/")[-1].lower()
        out = out_dir / f"{slug}.json"
        log = out_dir / "logs" / f"{slug}.log"
        if args.skip_existing and out.exists():
            try:
                if not json.loads(out.read_text()).get("errors") and json.loads(out.read_text()).get("metrics"):
                    print(f"[skip] {mid}", flush=True)
                    continue
            except ValueError:
                pass
        ev = evict_until(args.min_free_gb, {mid}, cache_path)
        if ev:
            print(f"[evict] {ev} -> free {free_gb(cache_path):.1f} GB", flush=True)
        cmd = [sys.executable, args.runner, "--model", mid, "--task", entry["task"], "--out", str(out)]
        cmd += plan.get("common_args", []) + entry.get("args", [])
        for n in entry.get("notes", []):
            cmd += ["--note", n]
        print(f"[run] {' '.join(cmd)}", flush=True)
        t0 = time.time()
        with log.open("w", encoding="utf-8") as fh:
            rc = subprocess.call(cmd, stdout=fh, stderr=subprocess.STDOUT)
        dur = time.time() - t0
        status.append({"model": mid, "rc": rc, "minutes": round(dur / 60, 1)})
        print(f"[done] {mid} rc={rc} in {dur/60:.1f} min", flush=True)
        (out_dir / "plan_status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
        time.sleep(10)  # let the device return to idle before the next idle baseline
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
