"""aihwbench command-line interface.

The CLI is split into focused command-group modules; this package composes
them into a single parser. Entry points:

  - console script: ``aihwbench`` (pyproject.toml -> aihwbench.cli:main)
  - module invocation: ``python -m aihwbench.cli``
"""

from __future__ import annotations

import argparse

from .. import __version__
from . import benchmark as _benchmark
from . import dataset as _dataset
from . import reporting as _reporting
from . import repro as _repro
from . import system as _system

COMMAND_GROUPS = (_system, _benchmark, _reporting, _dataset, _repro)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aihwbench",
        description="AIHWBench - vendor-neutral local AI runtime benchmarking",
    )
    parser.add_argument("--version", action="version", version=f"aihwbench {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)
    for group in COMMAND_GROUPS:
        group.register(sub)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    ret: int = args.func(args)
    return ret


if __name__ == "__main__":
    raise SystemExit(main())
