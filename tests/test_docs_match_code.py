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
