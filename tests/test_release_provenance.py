"""Released artifacts must carry signed build provenance.

A checksum proves the bytes did not change in transit. It says nothing about
where they came from, and anyone can publish a checksum for anything. The
attestation is the half that ties an artifact to the workflow run that built
it, and it is the half a project whose entire argument is provenance cannot
afford to lose quietly.

It can be lost quietly. The step is six lines in a workflow that only runs on a
tag, so a removal would sit unnoticed until someone tried to verify a release
and found nothing to verify — by which point the unattested artifacts are
already published. Nothing checked it before this file.

The documentation had drifted the other way: the feature shipped in the release
workflow while `docs/security/supply-chain.md` still listed it under "Planned"
and the roadmap box was unticked. Understating what exists is a smaller failure
than overstating it, but it still leaves a reader unable to tell what they are
getting, so the doc is asserted here too.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

RELEASE = Path(".github/workflows/release.yml")
SUPPLY_CHAIN = Path("docs/security/supply-chain.md")

ATTEST_ACTION = "actions/attest-build-provenance"


@pytest.fixture(scope="module")
def release() -> str:
    return RELEASE.read_text(encoding="utf-8")


def test_the_release_workflow_attests_its_artifacts(release):
    assert ATTEST_ACTION in release, (
        "releases carry no build provenance, so a published wheel cannot be "
        "tied to the workflow run that produced it"
    )


def test_the_attestation_action_is_pinned_to_a_commit(release):
    """An unpinned action is someone else's code running with our signing
    identity, at whatever version they publish next."""
    match = re.search(rf"{re.escape(ATTEST_ACTION)}@([0-9a-f]{{40}})", release)
    assert match is not None, "the attestation action is not pinned to a full commit SHA"


def test_both_distributions_are_covered(release):
    """A wheel-only attestation leaves the sdist unsigned, and the sdist is
    what anyone building from source consumes."""
    start = release.index(ATTEST_ACTION)
    block = release[start : start + 400]
    assert "dist/*.whl" in block
    assert "dist/*.tar.gz" in block


def test_the_workflow_can_actually_sign(release):
    """Attestation needs `id-token: write` to get an OIDC token and
    `attestations: write` to store the result.

    Without them the step fails at release time — the one moment nobody wants
    to be debugging permissions, and after the artifacts already exist.
    """
    head = release[: release.index("jobs:")]
    assert "id-token: write" in head
    assert "attestations: write" in head


def test_attestation_happens_before_the_artifacts_are_uploaded(release):
    """Attesting after upload would publish the unattested copy."""
    attest = release.index(ATTEST_ACTION)
    upload = release.index("actions/upload-artifact")
    assert attest < upload


def test_the_documentation_does_not_call_a_shipped_feature_planned():
    """It did. The reader could not tell what a release actually carries."""
    doc = SUPPLY_CHAIN.read_text(encoding="utf-8")
    current, _, planned = doc.partition("## Planned")
    assert "attestation" in current.lower(), (
        "provenance attestation is missing from the current measures"
    )
    assert "attestation" not in planned.lower(), (
        "provenance attestation is listed as planned, but the release workflow ships it"
    )


def test_the_documentation_says_how_to_verify():
    """A provenance statement nobody knows how to check is decoration."""
    doc = SUPPLY_CHAIN.read_text(encoding="utf-8")
    assert "gh attestation verify" in doc
