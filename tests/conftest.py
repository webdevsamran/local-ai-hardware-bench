"""Anchor test runs to the repository root.

Tests reference repo-relative paths (results/, configs/) so they behave
identically no matter which directory pytest is invoked from.
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
os.chdir(REPO_ROOT)
