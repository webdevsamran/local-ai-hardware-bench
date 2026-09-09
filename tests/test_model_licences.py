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
    """Weights are pulled at benchmark time; none are committed."""
    repo = MANIFEST.resolve().parent.parent
    weights = [
        path
        for pattern in ("*.gguf", "*.safetensors", "*.bin", "*.onnx")
        for path in repo.rglob(pattern)
        if ".venv" not in path.parts and "node_modules" not in path.parts
    ]
    assert weights == [], f"model weights must not be committed: {weights[:3]}"
