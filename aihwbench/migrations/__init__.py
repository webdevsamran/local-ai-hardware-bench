"""Schema evolution and migration machinery.

Result documents carry an explicit ``schema_version``. Readers accept every
historical version; ``migrate`` upgrades old documents to the current
schema without altering measured values.

Published schema 1.0 results (see ``results/published/``) remain readable
forever — a regression test validates every committed result through the
current reader.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from ..schemas import validate_result
from ..versions import CURRENT_SCHEMA_VERSION, PROTOCOL_VERSION, SUPPORTED_SCHEMA_VERSIONS

__all__ = [
    "SUPPORTED_SCHEMA_VERSIONS",
    "migrate",
    "read_result",
    "MigrationError",
]


class MigrationError(ValueError):
    """Raised when a document cannot be migrated to the current schema."""


def _record_migration(migrated: dict[str, Any], from_version: str, migrator: str) -> None:
    """Record one migration step without erasing the ones before it.

    A 1.0 document migrated to 2.1 passes through 2.0, and each step used to
    overwrite `from_version` -- so the finished document claimed to have come
    from 2.0 when it came from 1.0. The origin is the interesting half of the
    provenance, so it is written once and kept; every migrator that touched
    the document is appended in order.
    """
    block = migrated.setdefault("migration", {})
    if not isinstance(block, dict):
        return
    block.setdefault("from_version", from_version)
    block["to_version"] = migrated.get("schema_version")
    chain = block.get("migrators")
    if not isinstance(chain, list):
        # Carry forward a single `migrator` written by an older version of
        # this module rather than dropping it.
        chain = [block["migrator"]] if isinstance(block.get("migrator"), str) else []
    chain.append(migrator)
    block["migrators"] = chain
    block["migrator"] = migrator


def _migrate_1_to_2(data: dict[str, Any]) -> dict[str, Any]:
    """Upgrade a schema 1.0 document to 2.0.

    1.0 documents are structurally valid 2.0 documents: 2.0 adds optional
    blocks (workload, provenance, telemetry trace reference, quality) and
    new metric fields that default to null ("not measured"). The migration
    is therefore additive: copy everything, bump the version, and record
    which migrator produced the document.

    The copy is deep and the input is never mutated, so migrations are pure
    and idempotent. The recorded ``migrator`` name is the canonical module
    path under the current package name (``aihwbench``), not the historical
    ``benchmark`` package that predates the rename.
    """
    migrated = deepcopy(data)
    # Its own target, not CURRENT_SCHEMA_VERSION. Stamping "current" here made
    # this migrator jump straight to whatever the newest version happened to
    # be, so `migrate` saw the target reached and never ran the intervening
    # steps -- a document would arrive labelled 2.1 without 2.1's migration
    # having touched it. Latent while 2.0 was current; live the moment it was
    # not.
    migrated["schema_version"] = "2.0"
    # 2.0 requires `protocol_version`, and 1.0 predates the field, so a
    # migrated 1.0 document failed formal 2.0 validation on a field the
    # migration was supposed to supply. `validate --formal` had therefore
    # never passed on any migrated 1.0 result.
    #
    # Stating "1" is a statement of fact rather than a default: protocol 1 is
    # the only measurement protocol that has ever existed, so it is the one
    # every 1.0 document was produced under.
    migrated.setdefault("protocol_version", PROTOCOL_VERSION)
    _record_migration(migrated, "1.0", "aihwbench.migrations._migrate_1_to_2")
    return migrated


def _migrate_2_0_to_2_1(data: dict[str, Any]) -> dict[str, Any]:
    """Upgrade a schema 2.0 document to 2.1.

    2.1 adds no fields. It *requires* the ones the comparison-safety
    classifier must read -- model name, runtime name/backend/device, and the
    iteration counts -- which 2.0 declared optional and nullable.

    So this migration cannot fabricate anything. A 2.0 document already
    carrying those fields is a 2.1 document; one missing them is not, and
    relabelling it would launder an incomparable result into a comparable-
    looking one. `read_result` validates after migrating, so such a document
    fails there with the field named rather than passing silently.
    """
    migrated = deepcopy(data)
    migrated["schema_version"] = "2.1"
    _record_migration(migrated, "2.0", "aihwbench.migrations._migrate_2_0_to_2_1")
    return migrated


_MIGRATIONS: dict[tuple[str, str], Any] = {
    ("1.0", "2.0"): _migrate_1_to_2,
    ("2.0", "2.1"): _migrate_2_0_to_2_1,
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
