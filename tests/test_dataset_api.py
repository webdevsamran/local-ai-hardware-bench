"""The published dataset API description.

The generated JSON files are already a public API: served from a stable path,
fetchable by anyone, and people will build against them whether or not they
are described. Describing them turns an accident into a contract, and states
which parts are promised and which may be reshaped.

The description is generated from the real files so it cannot claim a shape
they do not have.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

spec_module = importlib.import_module("scripts.generate_openapi")

SPEC_PATH = Path("web/public/api/openapi.json")
DATA_DIR = Path("web/public/data")


def test_the_published_description_is_current():
    """The same check CI runs."""
    assert SPEC_PATH.is_file(), "run scripts/generate_openapi.py"
    assert SPEC_PATH.read_text(encoding="utf-8") == (
        json.dumps(spec_module.build(), indent=2, sort_keys=True) + "\n"
    )


def test_every_documented_endpoint_actually_exists():
    """A description promising a file that is not served is worse than none."""
    spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    for path in spec["paths"]:
        served = DATA_DIR / Path(path).name
        assert served.is_file(), f"{path} is documented but not generated"


def test_every_served_file_is_documented():
    """The other direction: an undocumented file is an undeclared contract."""
    spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    documented = {Path(p).stem for p in spec["paths"]}
    for served in DATA_DIR.glob("*.json"):
        assert served.stem in documented, (
            f"{served.name} is served but not described; add it to "
            "scripts/generate_openapi.py ENDPOINTS"
        )


@pytest.mark.parametrize("name", sorted(spec_module.ENDPOINTS))
def test_every_endpoint_declares_its_stability(name):
    _summary, stability, _note = spec_module.ENDPOINTS[name]
    assert stability in {"stable", "unstable"}


def test_the_leaderboard_is_marked_unstable_and_explains_its_rank():
    """Its rank is within a comparison group, and a consumer must know that."""
    spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    description = spec["paths"]["/data/leaderboard.json"]["get"]["description"]
    assert "within" in description
    assert "not" in description and "global ranking" in description


def test_result_documents_are_marked_stable():
    """The one endpoint people will build on must carry a promise."""
    spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    assert "stable" in spec["paths"]["/data/results.json"]["get"]["tags"]


def test_the_spec_is_valid_openapi_3():
    spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    assert spec["openapi"].startswith("3.")
    assert spec["info"]["title"]
    assert spec["servers"]
    for path, ops in spec["paths"].items():
        assert path.startswith("/"), path
        assert "200" in ops["get"]["responses"]
