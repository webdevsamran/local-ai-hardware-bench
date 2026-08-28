"""Result trust states — the canonical lifecycle for published results.

Canonical states are lowercase. A result moves through an explicit
lifecycle owned by maintainers; states are never auto-granted and never
inferred from measurement data:

    unreviewed -> verified | community_validated -> flagged
                                                 -> invalidated | superseded

Historical documents (schema 1.0 era) may carry the uppercase spellings
``VERIFIED`` / ``COMMUNITY_VALIDATED`` / ``UNVERIFIED`` in
``reproducibility.trust``. Those are accepted on read and normalized;
they are never emitted by this module.

For documents that carry both the modern top-level ``trust_state`` and
the legacy nested field, ``effective_trust()`` defines the single
authoritative read order, eliminating the previous duplicate sources of
truth.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "UNREVIEWED",
    "VERIFIED",
    "COMMUNITY_VALIDATED",
    "FLAGGED",
    "INVALIDATED",
    "SUPERSEDED",
    "UNVERIFIED",  # deprecated alias of UNREVIEWED (import compatibility)
    "TRUST_STATES",
    "REVIEWED_STATES",
    "TERMINAL_STATES",
    "TRUST_DEFINITIONS",
    "trust_state",
    "effective_trust",
]

# --- Canonical lifecycle states (lowercase) --------------------------------

UNREVIEWED = "unreviewed"
VERIFIED = "verified"
COMMUNITY_VALIDATED = "community_validated"
FLAGGED = "flagged"
INVALIDATED = "invalidated"
SUPERSEDED = "superseded"

# Deprecated name kept for import compatibility with pre-unification code.
# It always was the default "not yet reviewed" state; the canonical value
# is UNREVIEWED.
UNVERIFIED = UNREVIEWED

TRUST_STATES = (
    UNREVIEWED,
    VERIFIED,
    COMMUNITY_VALIDATED,
    FLAGGED,
    INVALIDATED,
    SUPERSEDED,
)

# States a maintainer grants after human review.
REVIEWED_STATES = (VERIFIED, COMMUNITY_VALIDATED)

# States that remove a result from active comparison sets.
TERMINAL_STATES = (INVALIDATED, SUPERSEDED)

TRUST_DEFINITIONS = {
    UNREVIEWED: (
        "Default for new submissions. Not yet validated by the project or "
        "a reviewer; may contain errors."
    ),
    VERIFIED: (
        "Executed by the project on real hardware with the exact committed "
        "workload, schema-validated, privacy-scanned, and reviewed by a "
        "maintainer."
    ),
    COMMUNITY_VALIDATED: (
        "Submitted by a community contributor, schema-validated, "
        "privacy-scanned, and reviewed. Not independently reproduced by "
        "the project."
    ),
    FLAGGED: (
        "An automated check or reviewer marked this result as suspicious. "
        "Excluded from leaderboards pending review."
    ),
    INVALIDATED: (
        "Determined to be wrong (measurement error, corrupted artifact, "
        "misreported environment). Retained for history; never ranked."
    ),
    SUPERSEDED: (
        "Replaced by a corrected re-run (replacement_run_id points at the "
        "successor). Retained for history; never ranked."
    ),
}

# Legacy spellings accepted on read only. Canonical values are never
# rewritten into documents by this module — migration is explicit. Lookup
# is case-insensitive: candidates are case-folded before matching, so any
# casing of a legacy spelling normalizes.
_LEGACY_ALIASES = {
    "unverified": UNREVIEWED,
}


def trust_state(value: str | None) -> str:
    """Normalize any trust spelling to its canonical lowercase state.

    Matching is case-insensitive and whitespace-tolerant. Unknown, empty,
    or missing values become ``unreviewed`` — the least-privilege default.
    Legacy spellings (``UNVERIFIED`` etc.) map onto their canonical
    equivalents.
    """
    if not isinstance(value, str):
        return UNREVIEWED
    candidate = value.strip().lower()
    if candidate in TRUST_STATES:
        return candidate
    if candidate in _LEGACY_ALIASES:
        return _LEGACY_ALIASES[candidate]
    return UNREVIEWED


def effective_trust(result: dict[str, Any]) -> str:
    """Authoritative trust read for a result document.

    Read order (first present wins):

    1. top-level ``trust_state`` (canonical field),
    2. legacy ``reproducibility.trust`` (schema-1.0 era field).

    A present-but-unrecognizable top-level value resolves to
    ``unreviewed`` and deliberately does NOT fall through to the legacy
    field: a corrupted authoritative field must not resurrect the older
    one.
    """
    top = result.get("trust_state")
    if isinstance(top, str) and top.strip():
        return trust_state(top)
    legacy = (result.get("reproducibility") or {}).get("trust")
    if isinstance(legacy, str) and legacy.strip():
        return trust_state(legacy)
    return UNREVIEWED
