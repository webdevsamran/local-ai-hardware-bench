"""Source that CPython accepts but a security scanner cannot read.

CodeQL reported one warning on this repository, and it was not a
vulnerability: `aihwbench/analysis/speculative.py` could not be parsed, so it
was dropped from the analysis. The other 102 modules were scanned; that one was
not, for three weeks, and nothing anywhere went red. A parse error that costs
you a *build* announces itself. A parse error that costs you *analysis* looks
exactly like a clean result.

That is the failure mode this file exists for. A test suite that only runs
under CPython cannot notice it: `python -m py_compile` is perfectly happy with
the line that broke the extractor.

The construct
-------------

A raw f-string containing a backslash immediately followed by a doubled brace::

    rf"...(?:\\{{[^}}]*\\}})?..."

CPython resolves this in one pass -- `{{` is the f-string escape for a literal
brace, and the backslash before it is just a backslash, because the string is
raw. A parser that resolves backslash escapes *before* brace-doubling sees
`\\{` as an escaped brace, is left holding a single `{`, reads it as the start
of an interpolation, and never recovers.

The evidence for that reading is that two other raw f-strings in this
repository parse fine:

- `tests/test_frontend_hydration.py` has a backslash and no doubled braces;
- `tests/test_release_provenance.py` has doubled braces and no backslash
  before them.

Only the file combining the two failed. This pins the combination rather than
banning raw f-strings outright, which would forbid two constructs that
demonstrably work.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent

#: Directories CodeQL extracts. It is configured with no path filter, so this
#: is "every Python file in the repository" rather than a chosen subset.
_SCANNED = ("aihwbench", "scripts", "tests")

#: The hazardous sequences, assembled rather than written out so this module
#: does not trip its own check when the detector is later widened to scan
#: docstrings as well as f-string literals.
_BACKSLASH = chr(92)
_HAZARDS = (_BACKSLASH + "{{", _BACKSLASH + "}}")


def _python_files() -> list[Path]:
    return sorted(
        path
        for root in _SCANNED
        for path in (_ROOT / root).rglob("*.py")
        if "__pycache__" not in path.parts
    )


_FILES = _python_files()


def test_there_are_files_to_check() -> None:
    """A glob matching nothing would make every test below vacuous."""
    assert len(_FILES) >= 150, f"only found {len(_FILES)} Python files"


@pytest.mark.parametrize("path", _FILES, ids=lambda p: str(p.relative_to(_ROOT)))
def test_every_scanned_file_parses(path: Path) -> None:
    """The cheap half: CPython itself must be able to read it.

    This cannot catch the CodeQL failure -- CPython parsed the offending file
    without complaint -- but it is the floor, and it costs nothing.
    """
    source = path.read_text(encoding="utf-8")
    try:
        ast.parse(source, filename=str(path))
    except SyntaxError as exc:  # pragma: no cover - only on a genuine breakage
        pytest.fail(f"{path.relative_to(_ROOT)}:{exc.lineno}: {exc.msg}")


def _raw_fstrings(path: Path) -> list[tuple[int, str]]:
    """Every raw f-string literal in a file, with its line number.

    Located through the AST rather than by regex over the text: a regex would
    match the example inside a docstring -- including the ones in this module's
    own docstring -- and report a hazard in prose that no parser ever reads as
    code.
    """
    source = path.read_text(encoding="utf-8")
    found: list[tuple[int, str]] = []
    for node in ast.walk(ast.parse(source, filename=str(path))):
        if not isinstance(node, ast.JoinedStr):
            continue
        segment = ast.get_source_segment(source, node)
        if not segment:
            continue
        prefix = segment[: len(segment) - len(segment.lstrip("rRfFbB"))].lower()
        if "r" in prefix and "f" in prefix:
            found.append((node.lineno, segment))
    return found


@pytest.mark.parametrize("path", _FILES, ids=lambda p: str(p.relative_to(_ROOT)))
def test_no_raw_fstring_hides_a_brace_behind_a_backslash(path: Path) -> None:
    """The construct that made a module invisible to the security scanner.

    The fix is never difficult: the interpolation can be concatenated, which
    also makes the regex legible, since nobody reads a doubled brace as a
    literal one on the first pass.
    """
    offenders = [
        (line, segment)
        for line, segment in _raw_fstrings(path)
        if any(hazard in segment for hazard in _HAZARDS)
    ]
    assert not offenders, (
        f"{path.relative_to(_ROOT)} contains a raw f-string with a backslash "
        f"before a doubled brace, which CodeQL's Python extractor cannot parse "
        f"-- the whole file is then silently dropped from security analysis: "
        f"{offenders}. Concatenate the interpolation instead of using an "
        f"f-string; see aihwbench/analysis/speculative.py for the pattern."
    )
