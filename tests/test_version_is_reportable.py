"""`aihwbench --version` works today; this keeps it working and honest.

`PACKAGE_VERSION` in `aihwbench/versions.py` is written into published result
documents as provenance, so it is not only a display string: two results from
different releases that both claim the same version are not comparable, and
nothing downstream can tell. It has to track `pyproject.toml`.

The sibling project api-verity-lab carried a package `__version__` of "0.1.0"
against a declared 0.2.0 precisely because no test compared them.
"""

from __future__ import annotations

import pathlib

import pytest
import tomllib

from aihwbench import __version__
from aihwbench.cli import main
from aihwbench.versions import PACKAGE_VERSION

PYPROJECT = pathlib.Path(__file__).resolve().parents[1] / "pyproject.toml"


def _declared_version() -> str:
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    return str(data["project"]["version"])


def test_package_version_matches_pyproject() -> None:
    assert PACKAGE_VERSION == _declared_version()


def test_dunder_version_is_the_same_object_of_truth() -> None:
    assert __version__ == PACKAGE_VERSION


def test_version_flag_exits_zero_and_prints_the_version(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])
    assert excinfo.value.code == 0
    assert PACKAGE_VERSION in capsys.readouterr().out
