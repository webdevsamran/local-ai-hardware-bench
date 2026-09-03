"""Authoritative version constants for AIHWBench.

Single source of truth for the package, schema and protocol versions.
All consumers must import these constants from this module (never re-declare
their own), so the writer version, reader support and protocol identity can
never drift.

Writers emit ``CURRENT_SCHEMA_VERSION`` (currently 2.0). Readers accept every
version in ``SUPPORTED_SCHEMA_VERSIONS`` and migrate older documents forward
(see ``aihwbench/migrations``).

Changes to this file must be intentional and documented in ``CHANGELOG.md``:
they change the on-disk/data contract.
"""

from __future__ import annotations

# Package (distribution) version.
PACKAGE_VERSION = "0.1.0"

# Result-document schema version: the CURRENT writer version.
CURRENT_SCHEMA_VERSION = "2.0"

# Every schema version the reader can parse without migration.
# Anything older is migrated forward; anything newer is rejected with
# a clear "written by a newer version" error.
SUPPORTED_SCHEMA_VERSIONS: tuple[str, ...] = ("1.0", "2.0")

# Backwards-compatible alias kept for older imports. This is the historical
# schema version that early documents carry, NOT the current writer version.
# Prefer CURRENT_SCHEMA_VERSION / SCHEMA_VERSIONS for new code.
SCHEMA_VERSION = "1.0"

# Benchmark protocol version: identifies the measurement methodology
# (workload definitions, aggregation rules, telemetry policy).
# Bumped independently of the package version and result schema.
PROTOCOL_VERSION = "1"

__all__ = [
    "PACKAGE_VERSION",
    "CURRENT_SCHEMA_VERSION",
    "SUPPORTED_SCHEMA_VERSIONS",
    "SCHEMA_VERSION",
    "PROTOCOL_VERSION",
]
