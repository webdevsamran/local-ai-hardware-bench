"""Schema evolution and migration machinery.

Result documents carry an explicit ``schema_version``. Readers accept every
historical version; ``migrate`` upgrades old documents to the current
schema without altering measured values.

Published schema 1.0 results (see ``results/published/``) remain readable
forever — a regression test validates every committed result through the
current reader.
"""

from __future__ import annotations

from typing import Any

from ..schemas import CURRENT_SCHEMA_VERSION, validate_result

__all__ = [
    "SUPPORTED_SCHEMA_VERSIONS",
    "migrate",
    "read_result",
    "MigrationError",
]

SUPPORTED_SCHEMA_VERSIONS = ("1.0", "2.0")


class MigrationError(ValueError):
    """Raised when a document cannot be migrated to the current schema."""


def _migrate_1_to_2(data: dict[str, Any]) -> dict[str, Any]:
    """Upgrade a schema 1.0 document to 2.0.

    1.0 documents are structurally valid 2.0 documents: 2.0 adds optional
    blocks (workload, provenance, telemetry trace reference, quality) and
    new metric fields that default to null ("not measured"). The migration
    is therefore additive: copy everything, bump the version, and record
    which migrator produced the document.
    """
    migrated = dict(data)
    migrated["schema_version"] = "2.0"
    migrated.setdefault("migration", {})
    if isinstance(migrated["migration"], dict):
        migrated["migration"]["from_version"] = "1.0"
        migrated["migration"]["migrator"] = "benchmark.migrations._migrate_1_to_2"
    return migrated


_MIGRATIONS: dict[tuple[str, str], Any] = {
    ("1.0", "2.0"): _migrate_1_to_2,
}


def migrate(data: Any, target_version: str | None = None) -> dict[str, Any]:
    """Migrate a result document forward to ``target_version`` (default current).

    Raises :class:`MigrationError` for unknown versions or missing paths.
    Never modifies measured metrics.
    """
    if not isinstance(data, dict):
        raise MigrationError("result document must be a JSON object")
    version = data.get("schema_version")
    target = target_version or CURRENT_SCHEMA_VERSION
    if version not in SUPPORTED_SCHEMA_VERSIONS:
        raise MigrationError(
            f"unsupported schema_version {version!r}; supported: {SUPPORTED_SCHEMA_VERSIONS}"
        )
    if target not in SUPPORTED_SCHEMA_VERSIONS:
        raise MigrationError(f"unsupported target schema_version {target!r}")
    doc: dict[str, Any] = data
    while doc.get("schema_version") != target:
        step = (doc.get("schema_version"), target)
        # Only single-step migrations exist today; walk one step at a time.
        next_versions = [
            to for (frm, to), _fn in _MIGRATIONS.items() if frm == doc.get("schema_version")
        ]
        if not next_versions:
            raise MigrationError(f"no migration path from {step}")
        fn = _MIGRATIONS[(doc.get("schema_version"), next_versions[0])]
        doc = fn(doc)
    return doc


def read_result(data: Any) -> dict[str, Any]:
    """Read any supported historical version and return it at the current schema.

    This is the single entry point result readers should use. Validation
    errors after migration indicate corruption, not version drift.
    """
    migrated = migrate(data)
    errors = validate_result(migrated)
    if errors:
        bullet = chr(10) + "  - "
        raise MigrationError("document invalid after migration:" + bullet + bullet.join(errors))
    return migrated
