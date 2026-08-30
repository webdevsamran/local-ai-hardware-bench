"""Dataset versioning (#41).

Generates a versioned snapshot manifest for the published-results
directory: counts per runtime/model, SHA-256 of every member file, and an
explicit changes list versus the previous manifest (added/removed/changed
run ids). Snapshots are append-only artifacts; nothing is deleted.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

__all__ = ["build_snapshot_manifest", "diff_snapshots"]

SCHEMA_VERSION = "1.0"


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_snapshot_manifest(
    results_dir: Path,
    version: str,
    previous_manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a snapshot manifest over all *.json results in results_dir."""
    files = sorted(results_dir.glob("*.json"))
    members = {p.name: _sha256_file(p) for p in files}

    run_ids: list[str] = []
    by_runtime: dict[str, int] = {}
    by_model: dict[str, int] = {}
    for p in files:
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(
                f"cannot snapshot {p.name}: unreadable or invalid JSON — {exc}. "
                "A snapshot must account for every member file; aborting."
            ) from exc
        run_id = doc.get("run_id") or p.stem
        run_ids.append(run_id)
        runtime = ((doc.get("runtime") or {}).get("name")) or "unknown"
        model = ((doc.get("model") or {}).get("name")) or "unknown"
        by_runtime[runtime] = by_runtime.get(runtime, 0) + 1
        by_model[model] = by_model.get(model, 0) + 1

    changes: dict[str, Any] | None = None
    if previous_manifest:
        prev_members = previous_manifest.get("members", {})
        added = sorted(set(members) - set(prev_members))
        removed = sorted(set(prev_members) - set(members))
        changed = sorted(
            name for name in set(members) & set(prev_members) if members[name] != prev_members[name]
        )
        changes = {"added": added, "removed": removed, "changed": changed, "invalidated": []}
    return {
        "schema_version": SCHEMA_VERSION,
        "version": version,
        "results_count": len(run_ids),
        "run_ids": run_ids,
        "counts_by_runtime": by_runtime,
        "counts_by_model": by_model,
        "members": members,
        "changes_vs_previous": changes,
    }


def diff_snapshots(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """Compare two snapshot manifests."""
    old_members = old.get("members", {})
    new_members = new.get("members", {})
    return {
        "old_version": old.get("version"),
        "new_version": new.get("version"),
        "added": sorted(set(new_members) - set(old_members)),
        "removed": sorted(set(old_members) - set(new_members)),
        "changed": sorted(
            n for n in set(old_members) & set(new_members) if old_members[n] != new_members[n]
        ),
    }
