"""Allow ``python -m aihwbench.cli`` to execute the CLI."""

from . import main

raise SystemExit(main())
