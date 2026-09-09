"""Generate the OpenAPI description of the public dataset API.

Usage:
    python scripts/generate_openapi.py            # write
    python scripts/generate_openapi.py --check    # verify freshness

The dashboard's generated JSON files are already a public API: they are
served from a stable path, anyone can fetch them, and people will build
against them whether or not they are described. Describing them turns an
accident into a contract — and, more usefully, states which parts are
promised and which may change.

It is generated from the real files rather than hand-written, so the
description cannot drift from what is actually served. CI checks freshness.

There is no server here and none is implied: this documents static files on
a CDN, which is the whole point. A benchmark dataset that needs a running
service to read is a dataset that stops existing when someone stops paying
for it.
"""

from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aihwbench.versions import (  # noqa: E402
    CURRENT_SCHEMA_VERSION,
    PACKAGE_VERSION,
    PROTOCOL_VERSION,
)

DATA_DIR = ROOT / "web" / "public" / "data"
OUT = ROOT / "web" / "public" / "api" / "openapi.json"
BASE_URL = "https://webdevsamran.github.io/local-ai-hardware-bench"

#: What each file is, and how stable it is. Stability is stated per endpoint
#: because it genuinely differs: the result documents follow a versioned schema
#: with a migration path, while the dashboard's convenience views exist to
#: serve the dashboard and may be reshaped when it changes.
ENDPOINTS: dict[str, tuple[str, str, str]] = {
    "results": (
        "Every published benchmark result, in full.",
        "stable",
        "Each element follows the versioned result schema in `schemas/`. "
        "Breaking changes go through a schema version bump and a migration, "
        "never a silent reshape.",
    ),
    "index": (
        "Dataset counts and provenance.",
        "stable",
        "Small and unlikely to change shape.",
    ),
    "hardware": (
        "Every machine with published results, keyed by hardware fingerprint.",
        "stable",
        "The fingerprint is a stable identifier for a hardware configuration.",
    ),
    "runtimes": (
        "Every benchmarked runtime, with the versions and devices measured.",
        "stable",
        "",
    ),
    "models": (
        "Every benchmarked model, with formats, quantizations and checksums.",
        "stable",
        "",
    ),
    "comparability": (
        "The comparison-safety rule tables, and a verdict for every published pair.",
        "stable",
        "Generated from `aihwbench/comparability.py`. Consumers implementing "
        "the classifier themselves should read the rules from here rather "
        "than hardcoding them.",
    ),
    "constants": (
        "Bits-per-weight table and overhead factor for the model-fit estimator.",
        "stable",
        "Generated from `aihwbench/analysis/fit.py`, with reference vectors.",
    ),
    "leaderboard": (
        "Ranked views, grouped by comparison safety.",
        "unstable",
        "A convenience view for the dashboard. Rank is *within* a comparison "
        "group and never across the dataset; do not read it as a global "
        "ranking. Shape may change when the dashboard does.",
    ),
    "trends": (
        "Per-runtime measurements over time.",
        "unstable",
        "A convenience view for the dashboard.",
    ),
    "pareto": (
        "Pareto-optimal points for each efficiency frontier.",
        "unstable",
        "A convenience view for the dashboard.",
    ),
    "recommend": (
        "Reference recommendations from the configuration engine.",
        "unstable",
        "A convenience view for the dashboard's recommender, carrying "
        "reference cases that pin the browser implementation to the Python "
        "one. Recommendations themselves are computed per request, not served.",
    ),
    "tco": (
        "Reference vectors for the local-vs-cloud calculator.",
        "unstable",
        "Contains no pricing: cloud prices are supplied by the caller.",
    ),
}


def _shape(value: object, depth: int = 0) -> dict:
    """A JSON Schema fragment inferred from real data.

    Inferred rather than declared, so the description cannot claim a shape the
    files do not have. Depth is capped: past a couple of levels the useful
    information is "an object", and a fully expanded tree of every result field
    is noise.
    """
    if isinstance(value, bool):
        return {"type": "boolean"}
    if isinstance(value, int):
        return {"type": "integer"}
    if isinstance(value, float):
        return {"type": "number"}
    if isinstance(value, str):
        return {"type": "string"}
    if value is None:
        return {"type": "null"}
    if isinstance(value, list):
        if not value or depth >= 2:
            return {"type": "array"}
        return {"type": "array", "items": _shape(value[0], depth + 1)}
    if isinstance(value, dict):
        if depth >= 2:
            return {"type": "object"}
        return {
            "type": "object",
            "properties": {k: _shape(v, depth + 1) for k, v in list(value.items())[:40]},
        }
    return {}


def build() -> dict:
    paths: dict[str, dict] = {}
    for name, (summary, stability, note) in ENDPOINTS.items():
        source = DATA_DIR / f"{name}.json"
        if not source.is_file():
            continue
        payload = json.loads(source.read_text(encoding="utf-8"))
        description = summary
        if note:
            description += f"\n\n{note}"
        description += f"\n\n**Stability: {stability}.**"
        paths[f"/data/{name}.json"] = {
            "get": {
                "summary": summary,
                "description": description,
                "operationId": f"get{name.capitalize()}",
                "tags": ["stable" if stability == "stable" else "convenience views"],
                "responses": {
                    "200": {
                        "description": summary,
                        "content": {"application/json": {"schema": _shape(payload)}},
                    }
                },
            }
        }

    return {
        "openapi": "3.1.0",
        "info": {
            "title": "AIHWBench dataset",
            "version": PACKAGE_VERSION,
            "summary": "Read-only access to published local AI benchmark results.",
            "description": (
                "Static JSON served from GitHub Pages. There is no server and "
                "no authentication: every file is a plain GET, cacheable and "
                "mirrorable.\n\n"
                "That is deliberate. A benchmark dataset behind a running "
                "service stops existing when someone stops paying for it; one "
                "that is a set of files in a public repository does not.\n\n"
                f"Result documents follow schema version {CURRENT_SCHEMA_VERSION} "
                f"and protocol version {PROTOCOL_VERSION}. Endpoints marked "
                "**stable** change only through a versioned schema bump with a "
                "migration path. Endpoints marked **unstable** are convenience "
                "views for the dashboard and may be reshaped.\n\n"
                "The rank in `leaderboard.json` is *within* a comparison group, "
                "never across the dataset. Two results in different groups are "
                "not ranked against each other, and treating them as if they "
                "were is the mistake this project exists to prevent."
            ),
            "license": {
                "name": "Apache-2.0",
                "url": "https://www.apache.org/licenses/LICENSE-2.0",
            },
        },
        "servers": [{"url": BASE_URL, "description": "Published dataset"}],
        "tags": [
            {
                "name": "stable",
                "description": "Versioned; breaking changes require a schema bump.",
            },
            {
                "name": "convenience views",
                "description": "Shaped for the dashboard; may change with it.",
            },
        ],
        "paths": paths,
    }


def main() -> int:
    spec = build()
    text = json.dumps(spec, indent=2, sort_keys=True) + "\n"
    if "--check" in sys.argv:
        if not OUT.is_file():
            print(f"error: {OUT} is missing; run without --check", file=sys.stderr)
            return 1
        if OUT.read_text(encoding="utf-8") != text:
            print(
                f"error: {OUT} is stale. The dataset files changed shape without "
                "regenerating the API description. Run: "
                "python scripts/generate_openapi.py",
                file=sys.stderr,
            )
            return 1
        print(f"{OUT} matches the published data")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT} ({len(spec['paths'])} endpoints)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
