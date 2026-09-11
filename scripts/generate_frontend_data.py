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
import re
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
# Allow running as `python scripts/generate_frontend_data.py` without an
# installed package by placing the repo root on sys.path.
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
RESULTS_DIR = REPO / "results" / "published"
SWEEPS_DIR = REPO / "results" / "sweeps"
OUT_DIR = REPO / "web" / "public" / "data"

from aihwbench.analysis.cost import compare_local_vs_cloud  # noqa: E402
from aihwbench.analysis.fit import BITS_PER_WEIGHT, estimate_model_fit  # noqa: E402
from aihwbench.analysis.recommend import recommend_configuration  # noqa: E402
from aihwbench.comparability import (  # noqa: E402
    _CONDITIONAL,
    _REQUIRED_PRESENT,
    _STRICT,
    INSUFFICIENT_METADATA,
    compare_classification,
)
from aihwbench.export import comparison_groups, group_label  # noqa: E402
from aihwbench.metrics import performance_per_watt_unit  # noqa: E402
from aihwbench.modelzoo import ZooError, entry_for_checksum, load_zoo  # noqa: E402
from aihwbench.sweep import pareto_frontier  # noqa: E402
from aihwbench.trust import effective_trust  # noqa: E402

# Cases the browser-side estimator must reproduce exactly. They are computed
# here by the canonical Python implementation and checked by web/tests, so the
# two cannot drift apart silently: a change to the arithmetic in either place
# fails the frontend test suite.
_FIT_REFERENCE_CASES = [
    ("7B", "q4_k_m", 8192.0, 32000.0, 4096),
    ("7B", "fp16", 8192.0, 32000.0, 4096),
    ("0.5B", "q4_k_m", 16384.0, 32000.0, 2048),
    ("70B", "q4_k_m", 24000.0, 64000.0, 8192),
    ("3B", "q8_0", 6000.0, 16000.0, 4096),
    ("13B", "unknown-quant", 12000.0, 32000.0, 4096),
    (None, "q4_k_m", 12000.0, 32000.0, 4096),
]


#: VRAM buckets, in the sizes consumer cards are actually sold in.
_VRAM_TIERS = (
    (0, "No discrete GPU"),
    (6, "<= 6 GB"),
    (8, "8 GB"),
    (12, "12 GB"),
    (16, "16 GB"),
    (24, "24 GB"),
    (48, "24-48 GB"),
)


def _vram_tier(vram_mb: object) -> str | None:
    """Bucket VRAM into a shopping tier; None when it was not recorded."""
    if not isinstance(vram_mb, (int, float)) or vram_mb <= 0:
        return None
    gb = float(vram_mb) / 1024.0
    for threshold, label in _VRAM_TIERS:
        if gb <= threshold + 0.5:
            return label
    return "> 48 GB"


# Cases the browser-side TCO calculator must reproduce. Same arrangement as
# the fit estimator: computed by the canonical Python implementation, replayed
# by web/tests through the TypeScript one.
_TCO_REFERENCE_CASES = [
    (20_000_000, 0.60, 1800.0, 0.30, 180.0, 45.0, 3),
    (10_000_000, 10.0, 1200.0, 0.0, 0.0, 100.0, 3),
    (1000, 0.01, 2000.0, 0.40, 300.0, 40.0, 3),
    (1_000_000, 2.0, None, None, None, None, 1),
    (5_000_000, 3.0, 900.0, 0.25, 220.0, 60.0, 5),
]


#: Efficiency frontiers the dashboard plots. Each is a pair of objectives with
#: the direction that counts as better, so a chart cannot silently invert one.
_FRONTIERS = (
    ("throughput_vs_power", "generation_tokens_per_second", True, "average_power_watts", False),
    ("throughput_vs_vram", "generation_tokens_per_second", True, "peak_vram_mb", False),
    ("throughput_vs_latency", "generation_tokens_per_second", True, "ttft_ms", False),
)


def _pareto_views(results: list[dict]) -> dict:
    """Pareto-optimal points for each frontier, computed by the canonical code.

    A frontier answers "which configurations are not beaten on both axes at
    once" -- the question behind every hardware purchase, and one a single
    ranked column cannot express. Computed here rather than in the browser so
    the site and the CLI agree on what is optimal.
    """
    views: dict[str, dict] = {}
    for name, x_metric, x_max, y_metric, y_max in _FRONTIERS:
        objectives = {x_metric: x_max, y_metric: y_max}
        points = []
        for r in results:
            metrics = r.get("metrics") or {}
            if any(metrics.get(m) is None for m in objectives):
                continue
            points.append(
                {
                    "run_id": r.get("run_id"),
                    "runtime": (r.get("runtime") or {}).get("name"),
                    "model": (r.get("model") or {}).get("name"),
                    "gpu": (r.get("system") or {}).get("gpu"),
                    "x": metrics[x_metric],
                    "y": metrics[y_metric],
                }
            )
        optimal = {
            row["run_id"]
            for row in pareto_frontier(
                [
                    r
                    for r in results
                    if all((r.get("metrics") or {}).get(m) is not None for m in objectives)
                ],
                objectives,
            )
        }
        for point in points:
            point["optimal"] = point["run_id"] in optimal
        views[name] = {
            "x_metric": x_metric,
            "y_metric": y_metric,
            "x_higher_is_better": x_max,
            "y_higher_is_better": y_max,
            "points": points,
            "excluded_missing_metrics": len(results) - len(points),
        }
    return views


def _tco_constants() -> dict:
    cases = []
    for tokens, price, hw, kwh, watts, tps, years in _TCO_REFERENCE_CASES:
        cases.append(
            {
                "tokens_per_month": tokens,
                "cloud_usd_per_million_tokens": price,
                "hardware_cost_usd": hw,
                "electricity_usd_per_kwh": kwh,
                "average_power_watts": watts,
                "generation_tokens_per_second": tps,
                "years": years,
                "expected": compare_local_vs_cloud(
                    tokens_per_month=tokens,
                    cloud_usd_per_million_tokens=price,
                    hardware_cost_usd=hw,
                    electricity_usd_per_kwh=kwh,
                    average_power_watts=watts,
                    generation_tokens_per_second=tps,
                    years=years,
                ),
            }
        )
    return {
        "note": (
            "cloud pricing is supplied by the reader, never bundled: provider "
            "prices change and a stale table would produce confident wrong "
            "answers"
        ),
        "reference_cases": cases,
    }


_RECOMMEND_CASES = [
    (24576, 64.0),
    (16384, 32.0),
    (12288, 32.0),
    (8192, 16.0),
    (6144, 16.0),
    (0, 32.0),
]


def _recommendation_constants(results: list[dict]) -> dict:
    """Reference recommendations from the canonical Python engine.

    The browser must reach the same conclusion as `aihwbench recommend` for a
    given machine, so the reference cases are computed here and replayed
    through the TypeScript implementation in web/tests.
    """
    cases = []
    for vram_mb, ram_gb in _RECOMMEND_CASES:
        system = {"gpu_vram_mb": vram_mb or None, "ram_gb": ram_gb}
        cases.append(
            {
                "gpu_vram_mb": vram_mb or None,
                "ram_gb": ram_gb,
                "expected": recommend_configuration(system, results),
            }
        )
    return {
        "note": (
            "recommendations are estimates from a memory budget and an assumed "
            "quantization density; measured results upgrade the evidence tier"
        ),
        "reference_cases": cases,
    }


def _offload_cliffs() -> dict:
    """Measured offload sweeps, with the cliff analysis applied.

    The dashboard already draws an offload curve on the fit page, but that one
    is computed from a memory estimate: it shows what share of a model would
    spill, not what that costs. This is the other half, and the half nobody
    publishes -- measured throughput at each offload setting, on real hardware.

    Curves are served with the environment they were measured in, because the
    cliff is a property of a particular GPU's memory and PCIe link as much as
    of the model. A curve without that is a shape with no subject.
    """
    from aihwbench.analysis.cliff import find_offload_cliff

    curves = []
    if SWEEPS_DIR.is_dir():
        for path in sorted(SWEEPS_DIR.glob("sweep-*.json")):
            sweep = json.loads(path.read_text(encoding="utf-8"))
            matrix = sweep.get("matrix") or []
            environment = sweep.get("environment") or {}
            analysis = find_offload_cliff(matrix)
            # A sweep over some other axis has no cliff to show; skipping it
            # is not a failure, and pretending otherwise would put an empty
            # chart on the page.
            if analysis.get("cliff_detected") is None:
                continue
            curves.append(
                {
                    "source": path.name,
                    "runtime": environment.get("runtime"),
                    "model": environment.get("model"),
                    "gpu": (environment.get("system") or {}).get("gpu"),
                    "gpu_vram_mb": (environment.get("system") or {}).get("gpu_vram_mb"),
                    "cpu": (environment.get("system") or {}).get("cpu"),
                    "timestamp": environment.get("timestamp"),
                    "analysis": analysis,
                    "points": [
                        {
                            "gpu_layers": row["params"].get("gpu_layers"),
                            "tokens_per_second": (row.get("metrics") or {}).get(
                                "generation_tokens_per_second"
                            ),
                            "ci95": (row.get("metrics") or {}).get("gen_tps_ci95"),
                            "cv": (row.get("metrics") or {}).get("generation_tps_cv"),
                            "peak_vram_mb": (row.get("metrics") or {}).get("peak_vram_mb"),
                        }
                        for row in matrix
                        if (row.get("params") or {}).get("gpu_layers") is not None
                    ],
                }
            )
    return {
        "curves": curves,
        "note": (
            "Measured throughput at each offload setting, not an estimate. "
            "Each curve is one machine with one model: where the cliff sits "
            "depends on PCIe generation and width, memory bandwidth, and how "
            "much VRAM the rest of the desktop is using, so these are for "
            "comparison against your own measurement rather than for citing."
        ),
    }


def _privacy_patterns() -> dict:
    """The privacy scanner's patterns, plus vectors pinning the two engines.

    The submission page scans a contributor's result in the browser before
    they share it, and a second hand-written copy of these expressions would
    eventually disagree with the CLI about whether a file is safe. The
    direction of that disagreement is the dangerous one: nobody notices a scan
    that has quietly stopped catching something until a leak is published.

    The vectors matter as much as the patterns. Python's `re` and JavaScript's
    RegExp agree on this subset, but "agree" is a claim worth testing rather
    than assuming -- so every probe ships with the ids Python matched, and
    web/tests replays them through the browser implementation.
    """
    from aihwbench.sanitize import pattern_registry

    # Strings chosen to exercise each pattern from both sides. The negatives
    # are the important half: a pattern matching everything would sail through
    # a positives-only check while making the scanner useless.
    probes = [
        "aa:bb:cc:dd:ee:ff",
        "AA-BB-CC-DD-EE-FF",
        "192.168.1.44",
        "2001:0db8:85a3:0000:0000:8a2e:0370:7334",
        "123-45-6789",
        "ghp_" + "a" * 36,
        "Bearer abcdef0123456789",
        r"C:\Users\samra\models",
        "/home/alice/models",
        "Serial Number: ABC123XYZ",
        "SN-12345678",
        "USERNAME",
        "someone@example.com",
        # Negatives: ordinary content a result legitimately contains.
        "NVIDIA GeForce RTX 3080 Ti Laptop GPU",
        "qwen2.5:0.5b-instruct-q4_K_M",
        "12th Gen Intel(R) Core(TM) i9-12900H",
        "generation_tokens_per_second",
        "2026-09-10T08:00:00Z",
        "serial",  # a bare CPU capability flag, not a leak
    ]

    patterns = pattern_registry()
    compiled = [
        (
            entry["id"],
            re.compile(entry["pattern"], re.IGNORECASE if entry["ignore_case"] else 0),
        )
        for entry in patterns
    ]
    cases = [
        {
            "text": probe,
            "matches": sorted({pid for pid, rx in compiled if rx.search(probe)}),
        }
        for probe in probes
    ]
    return {
        "patterns": patterns,
        "reference_cases": cases,
        "note": (
            "Generated from aihwbench/sanitize.py, which stays canonical. "
            "Detection is regex-based and deliberately over-eager: a false "
            "positive costs a contributor a second look, while a false "
            "negative publishes someone's home directory."
        ),
    }


def _comparability_rules(results: list[dict]) -> dict:
    """The classifier's rule tables, plus verdicts it produced.

    The dashboard must reach the same verdict as the CLI for any pair a reader
    selects, and the pair is chosen at runtime so it cannot be precomputed.
    The rules therefore travel to the browser as data, and reference verdicts
    computed here pin the TypeScript implementation to this one in
    web/tests -- the same anti-drift arrangement as the fit estimator.
    """
    cases = []
    # Every ordered pair of published results, plus the degenerate cases that
    # the presence gate exists to catch.
    for a in results:
        for b in results:
            verdict = compare_classification(a, b)
            cases.append(
                {
                    "a": a.get("run_id"),
                    "b": b.get("run_id"),
                    "classification": verdict["classification"],
                    "machine_reasons": verdict["machine_reasons"],
                }
            )
    empty = compare_classification({}, {})
    return {
        "strict": list(_STRICT),
        "conditional": list(_CONDITIONAL),
        "required_present": list(_REQUIRED_PRESENT),
        "insufficient_metadata_reason": INSUFFICIENT_METADATA,
        "reference_cases": cases,
        "empty_case": {
            "classification": empty["classification"],
            "machine_reasons": empty["machine_reasons"],
        },
    }


def _fit_constants() -> dict:
    """Constants and reference vectors for the browser-side fit estimator."""
    cases = []
    for params, quant, vram, ram, ctx in _FIT_REFERENCE_CASES:
        cases.append(
            {
                "parameters": params,
                "quantization": quant,
                "available_vram_mb": vram,
                "available_ram_mb": ram,
                "context_tokens": ctx,
                "expected": estimate_model_fit(params, quant, vram, ram, ctx),
            }
        )
    return {
        "bits_per_weight": dict(sorted(BITS_PER_WEIGHT.items())),
        "overhead_factor": 1.15,
        "note": (
            "bits-per-weight are format conventions, not measurements; an "
            "unknown quantization is refused rather than guessed"
        ),
        "reference_cases": cases,
    }


def _load_results(strict: bool = True) -> list[dict]:
    """Load published results.

    ``strict=True`` (the default; used by CI and publishing) fails closed
    on any unreadable or schema-invalid file — silent data loss is never
    acceptable when generating published frontend data. ``strict=False``
    (exploratory local use) warns and skips.
    """
    from aihwbench.schemas import validate_result

    problems: list[str] = []
    results = []
    for path in sorted(RESULTS_DIR.glob("*.json")):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            problems.append(f"{path.name}: unreadable JSON ({exc})")
            continue
        if not isinstance(doc, dict):
            problems.append(f"{path.name}: not a JSON object")
            continue
        errors = validate_result(doc)
        if errors:
            problems.append(f"{path.name}: schema invalid ({'; '.join(errors[:2])})")
            continue
        doc["_file"] = path.name
        results.append(doc)
    if problems:
        message = (
            f"cannot generate frontend data: {len(problems)} problem file(s) in "
            f"{RESULTS_DIR}:\n" + "\n".join(problems)
        )
        if strict:
            raise ValueError(message)
        print(f"WARN: {message}", file=sys.stderr)
    return results


def _metric(result: dict, key: str):
    return (result.get("metrics") or {}).get(key)


def _normalize(value: object) -> str:
    if not value:
        return ""
    return " ".join(str(value).split()).casefold()


def _hardware_fingerprint(system: dict) -> str:
    """Versioned hardware identity (v2).

    v1 hashed only CPU/GPU/NPU strings and merged distinct machines that
    shared a CPU model string. v2 normalizes strings (whitespace/case) and
    includes OS and RAM; the algorithm version is embedded in the key so
    regenerations remain comparable.
    """
    parts = [
        system.get("cpu"),
        system.get("gpu"),
        system.get("npu"),
        system.get("os"),
        system.get("ram_gb"),
    ]
    raw = "|".join(_normalize(p) for p in parts)
    return "hwfp-v2-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _attach_zoo(models: dict[str, dict]) -> None:
    """Attach licence and provenance from the model zoo to each model.

    A dashboard that tells you how fast a model runs, and nothing about
    whether you may use it, has answered the easier half of the question.

    Resolution is by checksum first, because that is an identity rather than a
    label, and it is what lets two results recording different *kinds* of hash
    for the same weights resolve to one entry. Name matching is the fallback
    for results that recorded no checksum at all.

    A model absent from the zoo gets `zoo: None` rather than a guessed
    licence. "Unknown" is the honest answer and the dashboard says so.
    """
    try:
        entries = load_zoo(REPO / "models" / "zoo.json")
    except ZooError:
        # The dataset must still build without a manifest; the pages then say
        # the licence is unrecorded, which is true.
        return

    def slug(value: str) -> str:
        stem = value.rsplit(".gguf", 1)[0].rsplit(".onnx", 1)[0].lower()
        return "".join(c for c in stem if c.isalnum())

    by_slug = {slug(e.key): e for e in entries}
    by_slug.update({slug(e.name): e for e in entries})

    for entry_data in models.values():
        matched = None
        for checksum in entry_data.get("checksums") or []:
            matched = entry_for_checksum(entries, checksum)
            if matched is not None:
                break
        resolved_by = "checksum"
        if matched is None:
            matched = by_slug.get(slug(entry_data["name"]))
            resolved_by = "name" if matched is not None else None

        if matched is None:
            entry_data["zoo"] = None
            continue

        source = matched.source
        entry_data["zoo"] = {
            "key": matched.key,
            "license": matched.license,
            "license_link": matched.license_link,
            "license_source": matched.license_source,
            "parameters": matched.parameters,
            "family": matched.family,
            "size_bytes": matched.size_bytes,
            "checksum": matched.checksum,
            "checksum_kind": matched.checksum_kind,
            "source_kind": source.get("kind"),
            "obtain": (
                f"ollama pull {source.get('ref')}"
                if source.get("kind") == "ollama"
                else source.get("url")
            ),
            # How the model was tied to this entry. Matching on a name is
            # weaker evidence than matching on a hash, and the page says which
            # it was rather than presenting both as equally certain.
            "resolved_by": resolved_by,
        }


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

    _attach_zoo(models)

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
        (r for r in results if _metric(r, "performance_per_watt") is not None),
        key=lambda r: (-_metric(r, "performance_per_watt"),),
    )

    # Rank within comparison groups, never across them. A global rank column
    # asserts that row 1 beat row 2, which the comparison-safety classifier
    # rejects for most pairs -- the dashboard must not claim what
    # results/dataset/LEADERBOARD.md refuses to claim.
    groups = comparison_groups(results)
    group_of: dict[str, int] = {}
    labels: dict[int, str] = {}
    for gi, group in enumerate(groups):
        labels[gi] = group_label(group)
        for member in group:
            group_of[member["run_id"]] = gi

    # Where each ranked metric's spread lives, when it was measured. A rank
    # with no interval behind it cannot distinguish a real gap from a tie.
    _SPREAD_KEYS = {
        "generation_tokens_per_second": ("gen_tps_ci95", "generation_tps_cv"),
        "total_latency_ms": ("ci95_latency_ms", None),
    }

    def _spread(r: dict, metric_key: str) -> tuple[list | None, float | None]:
        ci_key, cv_key = _SPREAD_KEYS.get(metric_key, (None, None))
        metrics = r.get("metrics") or {}
        ci = metrics.get(ci_key) if ci_key else None
        if not (isinstance(ci, (list, tuple)) and len(ci) == 2):
            ci = None
        cv = metrics.get(cv_key) if cv_key else None
        return (list(ci) if ci else None, cv)

    def view(rows: list[dict], metric_key: str) -> list[dict]:
        out: list[dict] = []
        seen_in_group: dict[int, int] = defaultdict(int)
        # The interval of whatever sorted first in each group, to say whether
        # the rows beneath it are actually behind or merely sorted lower.
        leader_ci: dict[int, list | None] = {}
        for r in rows:
            gi = group_of[r["run_id"]]
            seen_in_group[gi] += 1
            ci, cv = _spread(r, metric_key)
            if seen_in_group[gi] == 1:
                leader_ci[gi] = ci

            # Two measurements whose 95% intervals overlap are not
            # distinguishable at this sample size, so presenting one as
            # beating the other is a claim the data does not support. Rank is
            # kept -- it is the sort order -- but the tie is published
            # alongside it. Observed here: 281.65 tok/s [277.9, 285.4] over
            # 261.31 tok/s [240.6, 282.1], which is a tie printed as a
            # 20 tok/s lead.
            tied: bool | None = None
            top = leader_ci.get(gi)
            if seen_in_group[gi] == 1:
                tied = False if ci else None
            elif ci and top:
                tied = ci[0] <= top[1] and top[0] <= ci[1]

            out.append(
                {
                    "ci95": ci,
                    "cv": cv,
                    # None where the metric carries no measured interval:
                    # unknown, never "distinguishable".
                    "indistinguishable_from_rank_1": tied,
                    # Rank is per group and restarts at 1 in each; `group_size`
                    # lets the UI say "1 of 1", which is not a ranking.
                    "rank": seen_in_group[gi],
                    "group": gi,
                    "group_label": labels[gi],
                    "group_size": len(groups[gi]),
                    "run_id": r["run_id"],
                    "runtime": (r.get("runtime") or {}).get("name"),
                    "model": (r.get("model") or {}).get("name"),
                    "cpu": (r.get("system") or {}).get("cpu"),
                    "gpu": (r.get("system") or {}).get("gpu"),
                    # Filterable dimensions. VRAM is bucketed into the tiers
                    # people actually shop by rather than exposed raw, so the
                    # filter answers "does this fit a 12 GB card" instead of
                    # requiring the reader to do the arithmetic.
                    "vram_mb": (r.get("system") or {}).get("gpu_vram_mb"),
                    "vram_tier": _vram_tier((r.get("system") or {}).get("gpu_vram_mb")),
                    "quantization": (r.get("model") or {}).get("quantization"),
                    "device": (r.get("runtime") or {}).get("device"),
                    "trust": effective_trust(r),
                    "value": _metric(r, metric_key),
                    # tok/s/W and inf/s/W are different quantities; publishing
                    # the unit stops the view ranking them against each other.
                    "unit": performance_per_watt_unit(r.get("metrics") or {})
                    if metric_key == "performance_per_watt"
                    else None,
                }
            )
        return out

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
        "constants": _fit_constants(),
        "comparability": _comparability_rules(results),
        "privacy": _privacy_patterns(),
        "cliff": _offload_cliffs(),
        "tco": _tco_constants(),
        "pareto": _pareto_views(results),
        "recommend": _recommendation_constants(results),
    }


def main(argv: list[str] | None = None) -> int:
    strict = True
    if argv is not None:
        # --tolerant enables warning-and-skip for exploratory local use.
        if "--tolerant" in argv:
            strict = False
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    try:
        results = _load_results(strict=strict)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
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
