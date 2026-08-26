"""Result trust states for the community result pipeline.

Trust states describe how much confidence a reader should place in a
published result. They are never auto-granted: a maintainer must apply
them after validation.
"""

VERIFIED = "VERIFIED"
COMMUNITY_VALIDATED = "COMMUNITY_VALIDATED"
UNVERIFIED = "UNVERIFIED"

TRUST_STATES = (VERIFIED, COMMUNITY_VALIDATED, UNVERIFIED)

TRUST_DEFINITIONS = {
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
    UNVERIFIED: (
        "Provided for reference only. Not yet validated by the project "
        "or a reviewer; may contain errors."
    ),
}


def trust_state(value: str | None) -> str:
    """Normalize a trust state value; unknown/missing becomes UNVERIFIED."""
    if value in TRUST_STATES:
        return value
    return UNVERIFIED
