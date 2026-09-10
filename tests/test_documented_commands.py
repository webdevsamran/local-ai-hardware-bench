"""Every command in the documentation must parse against the real CLI.

Documentation drift is a bug, and this is the kind nobody notices: a flag gets
renamed, the docs keep the old name, and the only person who finds out is
somebody following the getting-started guide for a backend they have never
used. Four of those guides told readers to pass `--backend`, which has never
been a flag, and three told them `--model` where the runtime needs
`--model-path`.

Parsing is all this checks. It cannot tell whether a command does the right
thing, only whether the CLI would accept it at all -- which is exactly the
failure the four guides had.
"""

from __future__ import annotations

import contextlib
import io
import pathlib
import re

import pytest

from aihwbench.cli import build_parser

ROOT = pathlib.Path(__file__).resolve().parent.parent

#: Lines that look like a whole `aihwbench` invocation on their own.
_COMMAND = re.compile(r"^\s*(?:\$ )?(aihwbench [^\n|<>&]+)$", re.MULTILINE)

#: Tokens that mean the line is a template rather than a runnable command.
_PLACEHOLDER = ("<", "{", "...")

#: A shell line continuation: a trailing backslash and the newline after it.
_CONTINUATION = re.compile(r"\\\s*\n\s*")


def _documented_commands() -> list[tuple[str, str]]:
    docs = sorted(ROOT.glob("*.md")) + sorted((ROOT / "docs").rglob("*.md"))
    found: dict[str, str] = {}
    for doc in docs:
        # Join shell line continuations first, so a wrapped invocation is
        # checked as the one command it is rather than as its first line --
        # which would fail for missing the arguments on the lines below.
        text = _CONTINUATION.sub(" ", doc.read_text(encoding="utf-8"))
        for match in _COMMAND.finditer(text):
            command = match.group(1).strip().rstrip("\\").strip()
            # A trailing `# comment` is prose, not an argument.
            command = command.split("#", 1)[0].strip()
            if not command:
                continue
            if any(token in command for token in _PLACEHOLDER):
                continue
            found.setdefault(command, str(doc.relative_to(ROOT)))
    return sorted((cmd, doc) for cmd, doc in found.items())


DOCUMENTED = _documented_commands()


def test_documentation_contains_commands_to_check():
    """A regex that silently matches nothing would pass every test below."""
    assert len(DOCUMENTED) >= 20, f"only found {len(DOCUMENTED)} documented commands"


@pytest.mark.parametrize(
    ("command", "doc"),
    DOCUMENTED,
    ids=[f"{doc}::{cmd[:60]}" for cmd, doc in DOCUMENTED],
)
def test_documented_command_parses(command: str, doc: str) -> None:
    parser = build_parser()
    argv = command.split()[1:]
    try:
        # argparse writes usage to stderr and raises SystemExit; neither
        # belongs in the test output when the command is fine.
        with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
            parser.parse_args(argv)
    except SystemExit as exc:
        if exc.code not in (0, None):
            pytest.fail(
                f"{doc} documents a command the CLI rejects:\n"
                f"    {command}\n"
                "Either the docs are stale or the flag was renamed."
            )
