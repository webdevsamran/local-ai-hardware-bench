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

# Dataset-manifest format version. This is a separate contract from the
# result-document schema (aihwbench.versions): it versions the layout of
# dataset/index files produced for the frontend, not benchmark results.
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

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "version": version,
        "results_count": len(run_ids),
        "run_ids": run_ids,
        "counts_by_runtime": by_runtime,
        "counts_by_model": by_model,
        "members": members,
        "changes_vs_previous": None,
    }

    # The same comparison `diff_snapshots` performs. It used to be written
    # twice -- once here and once there -- so the two could drift into
    # disagreeing about what changed between the same pair of snapshots.
    if previous_manifest:
        diff = diff_snapshots(previous_manifest, manifest)
        manifest["changes_vs_previous"] = {
            "added": diff["added"],
            "removed": diff["removed"],
            "changed": diff["changed"],
            # Reserved for results superseded through `aihwbench invalidate`,
            # which is a deliberate act rather than a file-level difference.
            "invalidated": [],
        }
    return manifest


def diff_snapshots(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """Compare two snapshot manifests.

    The single implementation of "what changed between two snapshots":
    `build_snapshot_manifest` calls this rather than repeating the set
    arithmetic, and `aihwbench snapshot --diff` calls it to compare two
    manifests that already exist -- which the builder cannot do, since it
    needs a results directory to walk.

    `changed` compares content hashes, so a result edited in place is a change
    even though its filename did not move. That is the case worth catching: a
    published result that quietly differs from the one people cited.
    """
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
