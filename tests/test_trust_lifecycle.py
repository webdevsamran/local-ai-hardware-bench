"""Trust-state unification tests (P0 fix 5).

Proves the canonical lowercase lifecycle, legacy uppercase normalization,
the single authoritative read order (``effective_trust``), and that the
export/quality consumers migrated off the duplicate trust systems.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aihwbench.export import _row
from aihwbench.quality import data_quality_report
from aihwbench.trust import (
    COMMUNITY_VALIDATED,
    FLAGGED,
    REVIEWED_STATES,
    TERMINAL_STATES,
    TRUST_DEFINITIONS,
    TRUST_STATES,
    UNREVIEWED,
    UNVERIFIED,
    VERIFIED,
    effective_trust,
    trust_state,
)

REPO = Path(__file__).resolve().parent.parent
PUBLISHED = REPO / "results" / "published"


# --- Canonical lifecycle -----------------------------------------------------


def test_canonical_states_are_lowercase_and_complete():
    assert TRUST_STATES == (
        "unreviewed",
        "verified",
        "community_validated",
        "flagged",
        "invalidated",
        "superseded",
    )
    assert TRUST_STATES == tuple(s.lower() for s in TRUST_STATES)
    assert set(TRUST_DEFINITIONS) == set(TRUST_STATES)


def test_deprecated_alias_matches_unreviewed():
    # Pre-unification importers use UNVERIFIED; it must keep working and
    # carry the canonical default value.
    assert UNVERIFIED == UNREVIEWED == "unreviewed"


def test_reviewed_and_terminal_partitions():
    assert set(REVIEWED_STATES) == {"verified", "community_validated"}
    assert set(TERMINAL_STATES) == {"invalidated", "superseded"}
    assert not set(REVIEWED_STATES) & set(TERMINAL_STATES)


# --- Normalization -----------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("VERIFIED", "verified"),
        ("Verified", "verified"),
        ("verified", "verified"),
        ("COMMUNITY_VALIDATED", "community_validated"),
        ("UNVERIFIED", "unreviewed"),
        ("unverified", "unreviewed"),
        ("flagged", "flagged"),
        ("INVALIDATED", "invalidated"),
        ("Invalidated", "invalidated"),
        ("SUPERSEDED", "superseded"),
        ("superseded", "superseded"),
        ("  verified  ", "verified"),  # surrounding whitespace tolerated
        ("VERIFIED ", "verified"),  # trailing whitespace tolerated
    ],
)
def test_legacy_spellings_normalize_to_canonical(raw: str, expected: str):
    assert trust_state(raw) == expected


@pytest.mark.parametrize("raw", [None, "", "   ", "bogus", "unreviewd", 42, object()])
def test_unknown_or_missing_becomes_unreviewed(raw):
    assert trust_state(raw) == UNREVIEWED


# --- Authoritative read order -------------------------------------------------


def _doc(top: str | None = None, legacy: str | None = None) -> dict:
    doc: dict = {"run_id": "r1", "reproducibility": {}}
    if top is not None:
        doc["trust_state"] = top
    if legacy is not None:
        doc["reproducibility"]["trust"] = legacy
    return doc


def test_legacy_only_document_migrates_deterministically():
    # Schema-1.0 era result: only reproducibility.trust exists.
    assert effective_trust(_doc(legacy="VERIFIED")) == VERIFIED
    assert effective_trust(_doc(legacy="COMMUNITY_VALIDATED")) == COMMUNITY_VALIDATED
    assert effective_trust(_doc(legacy="UNVERIFIED")) == UNREVIEWED


def test_top_level_takes_precedence_over_legacy():
    assert effective_trust(_doc(top="flagged", legacy="VERIFIED")) == FLAGGED
    assert effective_trust(_doc(top="verified", legacy="UNVERIFIED")) == VERIFIED


def test_corrupt_top_level_does_not_resurrect_legacy():
    # A corrupted authoritative field must not silently fall back.
    assert effective_trust(_doc(top="garbage", legacy="VERIFIED")) == UNREVIEWED


def test_missing_everything_is_unreviewed():
    assert effective_trust({"run_id": "r1"}) == UNREVIEWED
    assert effective_trust({"trust_state": None, "reproducibility": {"trust": ""}}) == UNREVIEWED


# --- Consumer integration -----------------------------------------------------


def test_quality_report_recognizes_community_validated():
    doc = _doc(top="community_validated")
    doc["metrics"] = {}
    report = data_quality_report(doc)
    assert report["checks"]["trust_state"] == COMMUNITY_VALIDATED


def test_quality_report_defaults_to_unreviewed():
    report = data_quality_report({"run_id": "r1", "metrics": {}})
    assert report["checks"]["trust_state"] == UNREVIEWED


def test_export_row_emits_canonical_value_from_legacy_document():
    # A schema-1.0 doc carrying only the legacy uppercase field must
    # export the canonical lowercase state — never the legacy spelling.
    doc = _doc(legacy="VERIFIED")
    doc.update(
        {
            "timestamp": "2026-01-01T00:00:00Z",
            "system": {},
            "runtime": {},
            "model": {},
            "metrics": {},
        }
    )
    row = _row(doc)
    assert row["trust"] == VERIFIED
    assert row["trust"] not in ("VERIFIED", "UNVERIFIED", "COMMUNITY_VALIDATED")


def test_export_row_prefers_top_level_trust_state():
    doc = _doc(top="flagged", legacy="VERIFIED")
    doc.update({"system": {}, "runtime": {}, "model": {}, "metrics": {}})
    assert _row(doc)["trust"] == FLAGGED


# --- Published corpus (real data, read-only) ----------------------------------


def test_every_published_result_resolves_to_verified():
    assert PUBLISHED.is_dir(), "published results directory missing"
    docs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(PUBLISHED.glob("*.json"))]
    assert docs, "no published results found"
    for doc in docs:
        assert effective_trust(doc) == VERIFIED, f"run {doc.get('run_id')} unexpected trust"
