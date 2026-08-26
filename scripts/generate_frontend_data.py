#!/usr/bin/env python3
"""Generate canonical static JSON for the web frontend.

Reads ``results/published/*.json`` and writes deterministic index files to
``web/public/data/``:

- index.json        dataset metadata + counts
- results.json      all published results (verbatim documents)
- hardware.json     hardware fingerprints with their result references
- runtimes.json     runtime index with versions and result references
- models.json       model index with formats/quantizations
- leaderboard.json  sorted views (throughput, TTFT, perf/watt)
- trends.json       per-runtime history across timestamps

Deterministic: identical inputs produce byte-identical outputs (sorted
keys, stable ordering). CI re-runs this and fails if output drifts.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RESULTS_DIR = REPO / "results" / "published"
OUT_DIR = REPO / "web" / "public" / "data"


def _load_results() -> list[dict]:
    results = []
    for path in sorted(RESULTS_DIR.glob("*.json")):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"WARN: skipping unreadable {path.name}: {exc}", file=sys.stderr)
            continue
        doc["_file"] = path.name
        results.append(doc)
    return results


def _metric(result: dict, key: str):
    return (result.get("metrics") or {}).get(key)


def _hardware_fingerprint(system: dict) -> str:
    parts = [system.get("cpu"), system.get("gpu"), system.get("npu")]
    raw = "|".join(str(p) for p in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def build(results: list[dict]) -> dict[str, object]:
    hardware: dict[str, dict] = {}
    runtimes: dict[str, dict] = {}
    models: dict[str, dict] = {}
    for r in results:
        system = r.get("system") or {}
        fp = _hardware_fingerprint(system)
        entry = hardware.setdefault(
            fp,
            {
                "fingerprint": fp,
                "cpu": system.get("cpu"),
                "gpu": system.get("gpu"),
                "npu": system.get("npu"),
                "os": system.get("os"),
                "ram_gb": system.get("ram_gb"),
                "result_ids": [],
            },
        )
        entry["result_ids"].append(r["run_id"])

        rt = r.get("runtime") or {}
        name = rt.get("name") or "unknown"
        rentry = runtimes.setdefault(
            name,
            {"name": name, "versions": [], "device_options": [], "result_ids": []},
        )
        if rt.get("version") and rt["version"] not in rentry["versions"]:
            rentry["versions"].append(rt["version"])
        if rt.get("device") and rt["device"] not in rentry["device_options"]:
            rentry["device_options"].append(rt["device"])
        rentry["result_ids"].append(r["run_id"])

        model = r.get("model") or {}
        mname = model.get("name") or "unknown"
        mentry = models.setdefault(
            mname,
            {
                "name": mname,
                "format": model.get("format"),
                "quantizations": [],
                "checksums": [],
                "result_ids": [],
            },
        )
        q = model.get("quantization")
        if q and q not in mentry["quantizations"]:
            mentry["quantizations"].append(q)
        csum = model.get("checksum")
        if csum and csum not in mentry["checksums"]:
            mentry["checksums"].append(csum)
        mentry["result_ids"].append(r["run_id"])

    def sort_key(r: dict):
        tps = _metric(r, "generation_tokens_per_second")
        return (tps is None, -(tps or 0))

    by_throughput = sorted(
        (r for r in results if _metric(r, "generation_tokens_per_second") is not None),
        key=sort_key,
    )
    by_ttft = sorted(
        (r for r in results if _metric(r, "ttft_ms") is not None),
        key=lambda r: (_metric(r, "ttft_ms"),),
    )
    by_perf_watt = sorted(
        (
            r
            for r in results
            if _metric(r, "performance_per_watt") is not None
        ),
        key=lambda r: (-_metric(r, "performance_per_watt"),),
    )

    def view(rows: list[dict], metric_key: str) -> list[dict]:
        return [
            {
                "rank": i + 1,
                "run_id": r["run_id"],
                "runtime": (r.get("runtime") or {}).get("name"),
                "model": (r.get("model") or {}).get("name"),
                "cpu": (r.get("system") or {}).get("cpu"),
                "gpu": (r.get("system") or {}).get("gpu"),
                "value": _metric(r, metric_key),
            }
            for i, r in enumerate(rows)
        ]

    trends: dict[str, list[dict]] = defaultdict(list)
    for r in sorted(results, key=lambda x: x.get("timestamp") or ""):
        rt = (r.get("runtime") or {}).get("name") or "unknown"
        trends[rt].append(
            {
                "timestamp": r.get("timestamp"),
                "version": (r.get("runtime") or {}).get("version"),
                "throughput": _metric(r, "generation_tokens_per_second"),
                "ttft_ms": _metric(r, "ttft_ms"),
            }
        )

    return {
        "index": {
            "schema_version": "1.0",
            "results_count": len(results),
            "hardware_count": len(hardware),
            "runtime_count": len(runtimes),
            "model_count": len(models),
            "source_dir": "results/published",
            "note": (
                "generated deterministically from published results; "
                "no synthetic benchmark numbers are included"
            ),
        },
        "results": results,
        "hardware": sorted(hardware.values(), key=lambda h: h["fingerprint"]),
        "runtimes": sorted(runtimes.values(), key=lambda x: x["name"]),
        "models": sorted(models.values(), key=lambda m: m["name"]),
        "leaderboard": {
            "throughput": view(by_throughput, "generation_tokens_per_second"),
            "ttft": view(by_ttft, "ttft_ms"),
            "perf_watt": view(by_perf_watt, "performance_per_watt"),
        },
        "trends": dict(sorted(trends.items())),
    }


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    results = _load_results()
    data = build(results)
    for key, payload in data.items():
        out_path = OUT_DIR / f"{key}.json"
        out_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + chr(10),
            encoding="utf-8",
        )
        print(f"written: {out_path.relative_to(REPO)}")
    print(f"results indexed: {len(results)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
