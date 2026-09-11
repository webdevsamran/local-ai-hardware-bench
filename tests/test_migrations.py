"""Tests for schema evolution and migrations."""

from __future__ import annotations

import copy
import json
import pathlib

import pytest

from aihwbench.migrations import (
    SUPPORTED_SCHEMA_VERSIONS,
    MigrationError,
    migrate,
    read_result,
)
from aihwbench.schemas import CURRENT_SCHEMA_VERSION, validate_result


def _published_docs() -> list[dict]:
    return [
        json.loads(p.read_text(encoding="utf-8"))
        for p in sorted(pathlib.Path("results/published").glob("*.json"))
    ]


def test_all_published_results_migrate_and_validate():
    """Published schema 1.0 results must remain readable forever."""
    docs = _published_docs()
    assert docs
    for doc in docs:
        migrated = read_result(copy.deepcopy(doc))
        assert migrated["schema_version"] == CURRENT_SCHEMA_VERSION
        # Measured values untouched by migration.
        assert migrated["metrics"] == doc["metrics"]


def test_migrate_records_provenance_of_migration():
    doc = _published_docs()[0]
    migrated = migrate(doc, target_version="2.0")
    assert migrated["migration"]["from_version"] == "1.0"
    assert migrated["metrics"] == doc["metrics"]


def test_migrate_rejects_unknown_version():
    with pytest.raises(MigrationError):
        migrate({"schema_version": "9.9"})


def test_migrate_rejects_non_object():
    with pytest.raises(MigrationError):
        migrate("not a dict")


def test_schema_2_document_validates_directly():
    doc = {
        "schema_version": "2.0",
        "run_id": "test-run-1",
        "timestamp": "2026-08-22T10:00:00Z",
        "system": {},
        "runtime": {},
        "model": {},
        "metrics": {"tpot_ms": 12.5, "error_rate": 0.01},
        "workload": {"id": "chat_short", "kind": "combined", "version": "1.0.0"},
        "provenance": {"result_hash": "a" * 64, "hash_algorithm": "sha256"},
        "quality": {"reproducibility_completeness": 72.5},
    }
    assert validate_result(doc) == []


def test_quality_score_bounds_enforced():
    doc = {
        "schema_version": "2.0",
        "run_id": "test-run-2",
        "timestamp": "2026-08-22T10:00:00Z",
        "system": {},
        "runtime": {},
        "model": {},
        "metrics": {},
        "quality": {"reproducibility_completeness": 150},
    }
    errors = validate_result(doc)
    assert any("reproducibility_completeness" in e for e in errors)


def test_error_rate_bounded_0_1():
    doc = {
        "schema_version": "2.0",
        "run_id": "test-run-3",
        "timestamp": "2026-08-22T10:00:00Z",
        "system": {},
        "runtime": {},
        "model": {},
        "metrics": {"error_rate": 1.5},
    }
    errors = validate_result(doc)
    assert any("error_rate" in e for e in errors)


def test_supported_versions_constant():
    """Pinned so a schema bump is a decision, not a side effect.

    Every historical version stays supported: results published under 1.0
    remain readable forever, which is the promise that makes the corpus worth
    contributing to.
    """
    assert "1.0" in SUPPORTED_SCHEMA_VERSIONS
    assert "2.0" in SUPPORTED_SCHEMA_VERSIONS
    assert CURRENT_SCHEMA_VERSION == "2.1"


def test_every_supported_version_has_a_formal_schema():
    """A version readers accept but no schema describes cannot be validated.

    `validate --formal` would silently have nothing to check it against.
    """
    from aihwbench.formal_schema import load_formal_schema

    for version in SUPPORTED_SCHEMA_VERSIONS:
        assert load_formal_schema(version), f"no formal schema for {version}"


def test_a_multi_step_migration_records_where_the_document_came_from():
    """1.0 -> 2.1 passes through 2.0, and each step used to overwrite the
    origin -- so the finished document claimed to have come from 2.0.

    The origin is the interesting half of the provenance.
    """
    doc = {
        "schema_version": "1.0",
        "run_id": "r1",
        "timestamp": "2026-01-01T00:00:00Z",
        "system": {},
        "runtime": {"name": "ollama", "backend": "x", "device": "cuda"},
        "model": {"name": "m"},
        "metrics": {},
        "reproducibility": {"iterations": 8, "warmup_runs": 3},
    }
    migrated = migrate(doc)
    assert migrated["schema_version"] == "2.1"
    assert migrated["migration"]["from_version"] == "1.0"
    assert migrated["migration"]["to_version"] == "2.1"
    assert migrated["migration"]["migrators"] == [
        "aihwbench.migrations._migrate_1_to_2",
        "aihwbench.migrations._migrate_2_0_to_2_1",
    ]
