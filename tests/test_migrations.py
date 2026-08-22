"""Tests for schema evolution and migrations."""

from __future__ import annotations

import copy
import json
import pathlib

import pytest

from benchmark.migrations import (
    SUPPORTED_SCHEMA_VERSIONS,
    MigrationError,
    migrate,
    read_result,
)
from benchmark.schemas import CURRENT_SCHEMA_VERSION, validate_result


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
    assert "1.0" in SUPPORTED_SCHEMA_VERSIONS
    assert CURRENT_SCHEMA_VERSION == "2.0"
