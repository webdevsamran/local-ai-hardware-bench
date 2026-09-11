"""Every benchmark model tier must carry its licence.

The definition of done for this project includes not redistributing model
weights without a licence check. This project distributes none -- models are
pulled from upstream at benchmark time -- but it *tells people to download
them*, which carries the same obligation to state the terms.

A licence recorded without its source is an assertion; one recorded with the
URL it was read from and the date it was read is a citation someone can check.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

MANIFEST = Path(__file__).resolve().parent.parent / "configs" / "models.json"
TIERS = json.loads(MANIFEST.read_text(encoding="utf-8"))["tiers"]


@pytest.mark.parametrize("tier", sorted(TIERS))
def test_every_tier_records_a_licence(tier: str) -> None:
    assert TIERS[tier].get("license"), f"tier {tier} has no licence"


@pytest.mark.parametrize("tier", sorted(TIERS))
def test_every_licence_cites_where_it_was_read(tier: str) -> None:
    """An uncited licence is an assertion, not a fact a reader can verify."""
    source = TIERS[tier].get("license_source", "")
    assert source.startswith("https://"), f"tier {tier} licence has no source URL"


@pytest.mark.parametrize("tier", sorted(TIERS))
def test_every_licence_records_when_it_was_checked(tier: str) -> None:
    """Licences change; a reader needs to know how stale this is."""
    checked = TIERS[tier].get("license_verified", "")
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", checked), (
        f"tier {tier} needs an ISO date in license_verified, got {checked!r}"
    )


@pytest.mark.parametrize("tier", sorted(TIERS))
def test_every_tier_states_its_commercial_terms(tier: str) -> None:
    """The question a reader actually has before downloading."""
    assert TIERS[tier].get("commercial_use"), f"tier {tier} does not state commercial terms"


def test_non_permissive_licences_are_flagged_as_such():
    """A custom licence must not read like an open one.

    The default comparison tier is under a custom commercial agreement, which
    is materially different from Apache-2.0 and has to say so.
    """
    standard = TIERS["standard"]
    assert standard["license"] != "apache-2.0"
    assert "custom commercial" in standard["commercial_use"]


def test_the_manifest_ships_no_weights():
    """Weights are pulled at benchmark time; none are committed.

    Asks git what is *tracked* rather than scanning the working tree, because
    those are different questions and only the first is the invariant. The
    scan failed the moment anyone downloaded a model to benchmark -- which is
    what `aihwbench zoo fetch` does, into `models/` by default -- and reported
    a gitignored local file as though the repository were about to
    redistribute it.
    """
    import subprocess

    repo = MANIFEST.resolve().parent.parent
    listed = subprocess.run(
        ["git", "ls-files", "-z", "*.gguf", "*.safetensors", "*.bin", "*.onnx"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    if listed.returncode != 0:  # pragma: no cover - not a git checkout
        pytest.skip("not a git repository, so tracked files cannot be listed")
    tracked = [name for name in listed.stdout.split("\0") if name]
    assert tracked == [], f"model weights must not be committed: {tracked[:3]}"


def test_the_tiers_and_the_model_zoo_agree_about_licences():
    """Two records name the same models; drift between them is the risk.

    `configs/models.json` says which model each tier benchmarks and cites the
    page a maintainer read the licence from. `models/zoo.json` records what
    was actually measured and reads the licence out of the artifact. They
    answer different questions and both are worth having -- but where they
    describe the same model they must not disagree, or a reader gets a
    different answer depending on which file they opened.

    This is also a genuine cross-check: the tier licence was read off a web
    page by hand, and the zoo licence out of the GGUF header by code.
    """
    from aihwbench.modelzoo import load_zoo

    repo = MANIFEST.resolve().parent.parent
    by_ref = {
        str(e.source.get("ref")): e
        for e in load_zoo(repo / "models" / "zoo.json")
        if e.source.get("kind") == "ollama"
    }
    compared = 0
    for tier, spec in sorted(TIERS.items()):
        entry = by_ref.get(spec.get("ollama", ""))
        if entry is None or entry.license is None:
            continue
        compared += 1
        assert entry.license.lower() == str(spec["license"]).lower(), (
            f"tier {tier} records licence {spec['license']!r} but the "
            f"artifact states {entry.license!r}"
        )
    assert compared, "no tier overlaps the zoo, so nothing was cross-checked"
