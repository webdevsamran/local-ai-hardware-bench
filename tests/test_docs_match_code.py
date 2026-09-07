"""Documentation claims that are cheap to drift and expensive to get wrong.

Three separate documents described the trust-state vocabulary three different
ways, none of them matching `trust.py` -- two used `UNVERIFIED`, which the
code itself marks as a deprecated alias. These tests make the code the single
source of truth so the docs cannot silently diverge again.
"""

from __future__ import annotations

from pathlib import Path

from aihwbench.trust import TRUST_STATES

_ROOT = Path(__file__).resolve().parent.parent


def _read(name: str) -> str:
    return (_ROOT / name).read_text(encoding="utf-8")


def test_readme_documents_every_trust_state() -> None:
    readme = _read("README.md")
    missing = [s for s in TRUST_STATES if f"`{s}`" not in readme]
    assert not missing, f"README.md omits trust state(s): {missing}"


def test_faq_documents_every_trust_state() -> None:
    faq = _read("FAQ.md")
    missing = [s for s in TRUST_STATES if f"`{s}`" not in faq]
    assert not missing, f"FAQ.md omits trust state(s): {missing}"


def test_docs_do_not_define_the_deprecated_alias_as_a_state() -> None:
    """`UNVERIFIED` is a back-compat alias, not a state in its own right.

    Naming it while explaining that it is deprecated is fine and useful --
    what must not happen is listing it as a definition, which is how all
    three documents previously presented it.
    """
    for name in ("README.md", "FAQ.md", "ARCHITECTURE.md"):
        for line in _read(name).splitlines():
            stripped = line.strip()
            defines_it = stripped.startswith(
                ("- `UNVERIFIED`", "| `UNVERIFIED`")
            ) or stripped.startswith("`UNVERIFIED` —")
            assert not defines_it, f"{name} defines the deprecated alias as a trust state: {line!r}"


def test_referenced_schema_files_exist() -> None:
    """Every schema the README links to must actually be present."""
    readme = _read("README.md")
    for filename in ("result-1.0.schema.json", "result-2.0.schema.json"):
        if filename in readme:
            assert (_ROOT / "schemas" / filename).is_file(), (
                f"README references schemas/{filename}, which does not exist"
            )
    assert not (_ROOT / "schemas" / "result_schema.schema.json").exists(), (
        "the superseded duplicate schema is back"
    )


def test_every_schema_id_matches_its_filename() -> None:
    """A schema advertising another file's $id breaks reference resolution."""
    import json

    for path in sorted((_ROOT / "schemas").glob("*.schema.json")):
        schema_id = json.loads(path.read_text(encoding="utf-8")).get("$id", "")
        assert schema_id.endswith(path.name), (
            f"{path.name} advertises $id {schema_id!r}, which is a different file"
        )


def test_the_unreviewed_notice_stays_until_the_review_happens() -> None:
    """`docs/methodology.md` says it has not been externally reviewed.

    That notice is the honest half of publishing a methodology nobody outside
    the project has checked, and it is exactly the kind of caveat that gets
    quietly dropped in a later edit. Issue #21 tracked the review and was
    closed -- for tidiness, not because the review happened -- so the ROADMAP
    checkbox is now the only thing recording that it is still outstanding.
    This ties the two together: while the box is unchecked, the notice stays.
    """
    root = Path(__file__).resolve().parent.parent
    roadmap = (root / "ROADMAP.md").read_text(encoding="utf-8")
    methodology = (root / "docs" / "methodology.md").read_text(encoding="utf-8")

    reviewed = "- [x] **Methodology review with external maintainers" in roadmap
    unreviewed = "- [ ] **Methodology review with external maintainers" in roadmap
    assert reviewed or unreviewed, (
        "the ROADMAP entry for the methodology review was renamed; update this test "
        "with it rather than deleting it"
    )
    if unreviewed:
        assert "has not yet been externally reviewed" in methodology, (
            "the ROADMAP still says the external methodology review has not happened, "
            "but docs/methodology.md no longer says so. One of the two is now wrong."
        )
        assert (root / "docs" / "methodology-review.md").is_file(), (
            "the ROADMAP points readers at a review packet that does not exist"
        )
