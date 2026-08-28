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

__all__ = [
    "create_bundle",
    "verify_bundle",
    "BUNDLE_SUFFIX",
    "MAX_MEMBER_COUNT",
    "MAX_UNCOMPRESSED_BYTES",
    "MAX_COMPRESSION_RATIO",
]

BUNDLE_SUFFIX = ".aihwbench"
_MANIFEST_NAME = "MANIFEST.sha256"

# Safety caps: bundles from untrusted sources must not be able to exhaust
# memory/disk via zip bombs or member floods. Verification refuses to read
# any archive that violates these limits (checked from ZipInfo metadata
# before any member is decompressed).
MAX_MEMBER_COUNT = 64
MAX_UNCOMPRESSED_BYTES = 256 * 1024 * 1024
MAX_COMPRESSION_RATIO = 200.0


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


def _is_unsafe_member_name(name: str) -> bool:
    """True for absolute paths, traversal segments, drives or separators."""
    if not name:
        return True
    if name.startswith("/") or name.startswith("\\"):
        return True
    if "\\" in name:
        return True
    if len(name) > 1 and name[1] == ":":
        return True
    return ".." in name.split("/")


def _parse_manifest(text: str) -> tuple[dict[str, str], list[str]]:
    """Parse MANIFEST.sha256 strictly.

    Returns (digest_by_member, errors). Grammar: ``<64 hex>  <name>``
    exactly two spaces, one entry per member, no duplicates. Malformed
    entries are errors, never silently skipped.
    """
    expected: dict[str, str] = {}
    errors: list[str] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        digest, sep, name = line.partition("  ")
        digest = digest.strip()
        name = name.strip()
        if not sep or not digest or not name:
            errors.append(f"manifest line {lineno}: malformed entry")
            continue
        if len(digest) != 64 or any(c not in "0123456789abcdefABCDEF" for c in digest):
            errors.append(f"manifest line {lineno}: digest is not 64 hex chars")
            continue
        if name == _MANIFEST_NAME:
            errors.append(f"manifest line {lineno}: manifest must not list itself")
            continue
        if name in expected:
            errors.append(f"manifest line {lineno}: duplicate entry for {name!r}")
            continue
        expected[name] = digest.lower()
    if not expected and not errors:
        errors.append("manifest is empty")
    return expected, errors


def verify_bundle(bundle_path: Path, *, allow_extra_members: bool = False) -> dict[str, Any]:
    """Verify a bundle's integrity. Read-only and fail-closed.

    Checks every manifest checksum, and additionally rejects bundles that

    - contain members not listed in the manifest (unless
      ``allow_extra_members=True`` is explicitly passed for exploratory
      local use — the injected member still stays unchecksummed),
    - have a malformed/duplicate manifest, duplicate member names, or
      unsafe member names (absolute paths / traversal), or
    - exceed safety caps (member count, uncompressed size, compression
      ratio) — evaluated from archive metadata before decompression.
    """
    report: dict[str, Any] = {
        "valid": False,
        "members_checked": 0,
        "mismatches": [],
        "missing": [],
        "extra_members": [],
        "manifest_errors": [],
        "violations": [],
    }
    if not bundle_path.exists():
        report["reason"] = "bundle not found"
        return report
    try:
        with zipfile.ZipFile(bundle_path) as zf:
            infos = zf.infolist()
            names = [info.filename for info in infos]
            name_set = set(names)
            violations: list[str] = report["violations"]

            # Caps first, from metadata only — no decompression yet.
            if len(infos) > MAX_MEMBER_COUNT:
                violations.append(f"member count {len(infos)} exceeds limit {MAX_MEMBER_COUNT}")
            total_uncompressed = sum(info.file_size for info in infos)
            if total_uncompressed > MAX_UNCOMPRESSED_BYTES:
                violations.append(
                    f"uncompressed size {total_uncompressed} exceeds limit {MAX_UNCOMPRESSED_BYTES}"
                )
            for info in infos:
                if (
                    info.compress_size > 0
                    and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO
                ):
                    violations.append(
                        f"member {info.filename!r}: compression ratio "
                        f"{info.file_size / info.compress_size:.0f} exceeds "
                        f"limit {MAX_COMPRESSION_RATIO:.0f}"
                    )
            if len(name_set) != len(names):
                violations.append("archive contains duplicate member names")
            violations.extend(
                f"unsafe member name: {name!r}"
                for name in sorted(name_set)
                if _is_unsafe_member_name(name)
            )
            if violations:
                report["reason"] = "bundle violates archive safety limits"
                return report

            if _MANIFEST_NAME not in name_set or "result.json" not in name_set:
                report["reason"] = "missing required bundle members"
                return report

            try:
                manifest_text = zf.read(_MANIFEST_NAME).decode("utf-8")
            except UnicodeDecodeError as exc:
                report["reason"] = f"unreadable manifest: {exc}"
                return report
            expected, manifest_errors = _parse_manifest(manifest_text)
            report["manifest_errors"] = manifest_errors

            mismatches = report["mismatches"]
            missing = report["missing"]
            for name, digest in sorted(expected.items()):
                if name not in name_set:
                    missing.append(name)
                    continue
                if _sha256_bytes(zf.read(name)) != digest:
                    mismatches.append(name)
            report["members_checked"] = len(expected)

            extra = sorted(name_set - set(expected) - {_MANIFEST_NAME})
            report["extra_members"] = extra

            report["valid"] = not (
                mismatches or missing or manifest_errors or (extra and not allow_extra_members)
            )
            report["policy"] = (
                "extra members rejected"
                if extra and not allow_extra_members
                else "extra members tolerated (unchecksummed)"
                if extra
                else "strict"
            )
            return report
    except (zipfile.BadZipFile, OSError) as exc:
        report["reason"] = f"unreadable bundle: {exc}"
        return report
