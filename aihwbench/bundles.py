"""Portable result bundles (#36).

A ``.aihwbench`` bundle is a ZIP archive containing:

- ``result.json``          — the benchmark result document
- ``environment.json``     — optional full environment snapshot
- ``workload.json``        — optional workload manifest
- ``telemetry.json``       — optional raw telemetry trace
- ``MANIFEST.sha256``      — SHA-256 of every member file

``create_bundle`` writes the archive; ``verify_bundle`` recomputes every
checksum and reports tampering. Bundle contents are never modified in
place — verification is read-only.
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any

__all__ = ["create_bundle", "verify_bundle", "BUNDLE_SUFFIX"]

BUNDLE_SUFFIX = ".aihwbench"
_MANIFEST_NAME = "MANIFEST.sha256"


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def create_bundle(
    out_path: Path,
    result: dict[str, Any],
    environment: dict[str, Any] | None = None,
    workload: dict[str, Any] | None = None,
    telemetry: dict[str, Any] | None = None,
) -> Path:
    """Create a .aihwbench bundle. Returns the written path."""
    members: dict[str, bytes] = {"result.json": json.dumps(result, indent=2).encode("utf-8")}
    if environment is not None:
        members["environment.json"] = json.dumps(environment, indent=2).encode("utf-8")
    if workload is not None:
        members["workload.json"] = json.dumps(workload, indent=2).encode("utf-8")
    if telemetry is not None:
        members["telemetry.json"] = json.dumps(telemetry, indent=2).encode("utf-8")

    manifest_lines = [f"{_sha256_bytes(data)}  {name}" for name, data in sorted(members.items())]
    manifest = (chr(10).join(manifest_lines) + chr(10)).encode("utf-8")

    out_path = out_path.with_suffix(BUNDLE_SUFFIX)
    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, data in sorted(members.items()):
            zf.writestr(name, data)
        zf.writestr(_MANIFEST_NAME, manifest)
    return out_path


def verify_bundle(bundle_path: Path) -> dict[str, Any]:
    """Verify all checksums in a bundle. Read-only."""
    if not bundle_path.exists():
        return {"valid": False, "reason": "bundle not found"}
    try:
        with zipfile.ZipFile(bundle_path) as zf:
            names = set(zf.namelist())
            if _MANIFEST_NAME not in names or "result.json" not in names:
                return {"valid": False, "reason": "missing required bundle members"}
            expected: dict[str, str] = {}
            for line in zf.read(_MANIFEST_NAME).decode("utf-8").splitlines():
                if not line.strip():
                    continue
                digest, _, name = line.partition("  ")
                expected[name.strip()] = digest.strip()
            mismatches: list[str] = []
            missing: list[str] = []
            for name, digest in sorted(expected.items()):
                if name not in names:
                    missing.append(name)
                    continue
                actual = _sha256_bytes(zf.read(name))
                if actual != digest:
                    mismatches.append(name)
            extra = sorted(names - set(expected) - {_MANIFEST_NAME})
            return {
                "valid": not mismatches and not missing,
                "members_checked": len(expected),
                "mismatches": mismatches,
                "missing": missing,
                "extra_members": extra,
            }
    except (zipfile.BadZipFile, UnicodeDecodeError) as exc:
        return {"valid": False, "reason": f"unreadable bundle: {exc}"}
