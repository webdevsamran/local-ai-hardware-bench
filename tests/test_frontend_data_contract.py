"""The generated dataset, the browser and the prerenderer must agree.

Three places name the same set of data files: `generate_frontend_data.py`
writes them, `web/src/lib/data.ts` fetches them at runtime, and
`web/scripts/prerender.mjs` reads them to render static HTML.

Two of those are hand-maintained lists, and they drifted the moment a
fourteenth file was added. The browser fetched it; the prerenderer did not.
The prerenderer's own comment says what that costs:

    A file missing here does not crash the prerender -- seedDataset bypasses
    the runtime validator -- it silently renders the page's empty state into
    the static HTML, which is worse: the deployed page then ships wrong
    content.

Which is exactly right, and is why this is checked rather than remembered. A
search engine and a first-time visitor both see the prerendered HTML, so a
page that says "no data has been published yet" over a dataset that has it is
the version of the site most readers would meet.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DATA_TS = REPO / "web" / "src" / "lib" / "data.ts"
PRERENDER = REPO / "web" / "scripts" / "prerender.mjs"
DATA_DIR = REPO / "web" / "public" / "data"


def _listed_names(source: Path) -> list[str]:
    """Dataset file names from the array literal beginning with 'index'.

    Both files spell the list the same way, so one parser reads both.
    """
    text = source.read_text(encoding="utf-8")
    start = text.index("'index'")
    block = text[start : text.index("]", start)]
    return sorted(set(re.findall(r"'([a-z_]+)'", block)))


def test_the_browser_and_the_prerenderer_load_the_same_files():
    assert _listed_names(PRERENDER) == _listed_names(DATA_TS)


def test_every_listed_file_is_actually_generated():
    """A name in the list with no file behind it fails the whole dataset load.

    `assertDataset` fails closed, so this surfaces as a blank site rather than
    a missing section -- worth catching in a test that names the file.
    """
    missing = [name for name in _listed_names(DATA_TS) if not (DATA_DIR / f"{name}.json").is_file()]
    assert not missing, f"listed but not generated: {missing}"


def test_every_generated_file_is_actually_read():
    """The opposite drift: data generated, published, and read by nobody.

    This repository's most common defect is a capability that exists and is
    never reached, and a generated file nothing reads is that defect in data
    form.

    "Read" means either of the two ways the frontend consumes this data: the
    runtime fetch list, or a static import. `tco.json` is only ever imported,
    because it holds reference vectors that `web/tests` replays against the
    TypeScript port of the Python estimator -- a file the app never fetches
    and that would be wrong to delete.
    """
    listed = set(_listed_names(DATA_TS))
    sources = [
        path.read_text(encoding="utf-8")
        for directory in (REPO / "web" / "src", REPO / "web" / "tests", REPO / "web" / "scripts")
        if directory.is_dir()
        for path in directory.rglob("*")
        if path.suffix in {".ts", ".tsx", ".mjs", ".js"}
    ]
    unused = []
    for path in sorted(DATA_DIR.glob("*.json")):
        if path.stem in listed:
            continue
        if any(f"data/{path.name}" in source for source in sources):
            continue
        unused.append(path.stem)
    assert not unused, f"generated but neither fetched nor imported: {unused}"


def test_the_kv_cache_study_reaches_the_dashboard_intact():
    """The findings must survive the trip from sweep to page.

    The two configurations that cost more memory than they save are the whole
    point of publishing this study; a page that renders the table without them
    would recommend exactly what the measurements warn against.
    """
    payload = json.loads((DATA_DIR / "kvcache.json").read_text(encoding="utf-8"))
    studies = payload["studies"]
    assert studies, "no KV-cache study reached the dashboard"

    report = studies[0]["report"]
    assert report["geometry"], (
        "without the model's attention geometry the analytic cache column is "
        "absent, and the inversion is invisible"
    )
    inverted = [c for c in report["configurations"] if c.get("costs_more_than_baseline")]
    assert len(inverted) == 2, f"expected both measured inversions, got {len(inverted)}"
    for config in inverted:
        assert config["measured_vram_saved_mb"] < 0
        assert config["kv_cache_saved_mb"] > 0
