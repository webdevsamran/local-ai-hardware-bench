"""Source that CPython accepts but a security scanner cannot read.

CodeQL reported one warning on this repository, and it was not a
vulnerability: `aihwbench/analysis/speculative.py` could not be parsed, so it
was dropped from the analysis. The other 102 modules were scanned; that one was
not, for three weeks, and nothing anywhere went red. A parse error that costs
you a *build* announces itself. A parse error that costs you *analysis* looks
exactly like a clean result, and the file it silences is picked by accident
rather than by risk.

That is the failure mode this file exists for. A test suite that only runs
under CPython cannot notice it: `python -m py_compile` is perfectly happy with
the file that broke the extractor, and so is `ast.parse` at every
`feature_version` from 3.7 to 3.14.

The construct
-------------

PEP 263 lets a source file declare its encoding on line one or two, with a
**comment** matching ``coding[:=]\\s*([-\\w.]+)``. CPython enforces the comment
part. CodeQL's Python extractor applies the pattern to the first two lines
whether or not they are a comment.

The module's docstring opened:

    \"\"\"Speculative decoding: the acceptance rate, which decides ...

"de*coding: the*" matches. The extractor read the file's declared encoding as
``the``, looked up a codec by that name, found none, and could not decode the
file -- which is why the failure presented as a parse error with no offending
line. The runner log said so plainly once it was read:

    [WARN] .../aihwbench/analysis/speculative.py has encoding 'the'

Any first- or second-line prose ending a word in "coding" before a colon or
equals sign does it: "decoding:", "encoding:", "transcoding=". So the guard is
the PEP 263 pattern itself, applied the lax way a third-party reader applies
it, with the capture checked against the codec registry.

A correction worth keeping
--------------------------

This file first blamed a raw f-string on line 56 -- the module's only one, and
the only one in the package. That hypothesis survived a plausible elimination
(66 files carry em-dashes and none are flagged; two other raw f-strings parse
fine) and was still wrong: the fix shipped, and CodeQL failed on the very same
file for the very same reason. The lesson is in the method, not the hypothesis.
Narrowing by what is *unique* to the failing file found a real uniqueness that
was not the cause; reading the tool's own log found the cause in one line. The
log was available the entire time.
"""

from __future__ import annotations

import codecs
import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent

#: Directories CodeQL extracts. Its workflow sets no path filter, so this is
#: "every Python file in the repository" rather than a chosen subset.
_SCANNED = ("aihwbench", "scripts", "tests")

#: PEP 263's declaration pattern. Assembled from two halves so that this
#: module's own source does not contain the sequence it forbids -- the file
#: defining the rule would otherwise be the first to break it.
_PEP263 = re.compile("cod" + r"ing[:=]\s*([-\w.]+)")

#: How many leading lines a reader scans for the declaration. PEP 263 says one
#: or two; the extractor that failed here honours that much.
_DECLARATION_LINES = 2


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
def test_no_file_accidentally_declares_a_nonexistent_source_encoding(path: Path) -> None:
    """The defect that cost one module every security scan for three weeks.

    Checked against the codec registry rather than by banning the word: a real
    ``# -*- coding: utf-8 -*-`` header is legitimate and must keep working. It
    is only a defect when the captured name is not a codec, because then no
    reader applying PEP 263 laxly can decode the file at all.
    """
    lines = path.read_text(encoding="utf-8").split("\n")[:_DECLARATION_LINES]
    for number, line in enumerate(lines, start=1):
        match = _PEP263.search(line)
        if match is None:
            continue
        declared = match.group(1)
        try:
            codecs.lookup(declared)
        except LookupError:
            pytest.fail(
                f"{path.relative_to(_ROOT)}:{number} reads as a PEP 263 encoding "
                f"declaration of {declared!r}, which is not a codec. CPython "
                f"ignores it because the line is not a comment, but a reader "
                f"that applies the pattern to any of the first two lines cannot "
                f"decode this file -- CodeQL drops it from analysis entirely, "
                f"silently. Reword the line so a word ending in 'coding' is not "
                f"followed by ':' or '='.\n    {line.strip()[:100]}"
            )


@pytest.mark.parametrize("path", _FILES, ids=lambda p: str(p.relative_to(_ROOT)))
def test_every_scanned_file_parses(path: Path) -> None:
    """The floor: CPython itself must be able to read it.

    This cannot catch the defect above -- CPython parsed the offending file
    without complaint, which is the whole problem -- but it costs nothing and
    catches the ordinary breakage.
    """
    import ast

    source = path.read_text(encoding="utf-8")
    try:
        ast.parse(source, filename=str(path))
    except SyntaxError as exc:  # pragma: no cover - only on a genuine breakage
        pytest.fail(f"{path.relative_to(_ROOT)}:{exc.lineno}: {exc.msg}")
