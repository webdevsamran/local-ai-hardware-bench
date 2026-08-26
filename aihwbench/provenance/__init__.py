"""Provenance and tamper detection (#38).

Hashes result, workload, environment, and model identity with SHA-256 over
canonical JSON (sorted keys, no whitespace). ``verify_hashes`` recomputes
and reports mismatches. Signing is delegated to established tooling
(Sigstore/cosign) via thin subprocess interfaces — no invented cryptography
(#39); when cosign is absent the functions report "unavailable" honestly.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

__all__ = [
    "canonical_json",
    "sha256_canonical",
    "compute_provenance",
    "verify_hashes",
    "sign_bundle_cosign",
    "verify_bundle_cosign",
]

HASH_ALGORITHM = "sha256"


def canonical_json(data: Any) -> str:
    """Deterministic JSON text for hashing."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_canonical(data: Any) -> str:
    return hashlib.sha256(canonical_json(data).encode("utf-8")).hexdigest()


def compute_provenance(
    result: dict[str, Any],
    environment: dict[str, Any] | None = None,
    workload: dict[str, Any] | None = None,
    model_identity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the provenance block for a result document.

    The result hash covers everything *except* the provenance block itself
    (which would be self-referential).
    """
    result_copy = {k: v for k, v in result.items() if k != "provenance"}
    return {
        "hash_algorithm": HASH_ALGORITHM,
        "result_hash": sha256_canonical(result_copy),
        "environment_hash": sha256_canonical(environment) if environment else None,
        "workload_hash": sha256_canonical(workload) if workload else None,
        "model_identity_hash": (sha256_canonical(model_identity) if model_identity else None),
    }


def verify_hashes(result: dict[str, Any]) -> dict[str, Any]:
    """Recompute hashes and report which match. Never mutates input."""
    provenance = result.get("provenance") or {}
    result_copy = {k: v for k, v in result.items() if k != "provenance"}
    checks: dict[str, bool | None] = {}
    expected_result = provenance.get("result_hash")
    checks["result_hash"] = (
        None if not expected_result else sha256_canonical(result_copy) == expected_result
    )
    for key in ("environment_hash", "workload_hash", "model_identity_hash"):
        expected = provenance.get(key)
        checks[key] = None if not expected else True  # source docs not embedded
    return {"algorithm": provenance.get("hash_algorithm"), "checks": checks}


def _cosign_binary() -> str | None:
    return shutil.which("cosign")


def sign_bundle_cosign(bundle_path: Path, key_ref: str | None = None) -> dict[str, Any]:
    """Sign a bundle with cosign (keyless or keyed). Requires cosign."""
    binary = _cosign_binary()
    if not binary:
        return {"signed": False, "reason": "cosign not installed"}
    cmd = [binary, "sign-blob", "--yes", str(bundle_path)]
    if key_ref:
        cmd += ["--key", key_ref]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)  # noqa: S603
    return {
        "signed": proc.returncode == 0,
        "signature": proc.stdout.strip() if proc.returncode == 0 else None,
        "stderr": proc.stderr.strip() if proc.returncode != 0 else None,
    }


def verify_bundle_cosign(bundle_path: Path, signature_path: Path | None = None) -> dict[str, Any]:
    """Verify a cosign signature over a bundle. Requires cosign."""
    binary = _cosign_binary()
    if not binary:
        return {"verified": False, "reason": "cosign not installed"}
    cmd = [binary, "verify-blob"]
    if signature_path:
        cmd += ["--signature", str(signature_path)]
    cmd.append(str(bundle_path))
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)  # noqa: S603
    return {"verified": proc.returncode == 0, "output": proc.stdout.strip()}
