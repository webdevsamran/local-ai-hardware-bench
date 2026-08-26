"""Deterministic result fingerprints for duplicate detection and integrity.

A fingerprint is a stable digest over the comparison-relevant identity of
a result: protocol, model, workload, runtime, hardware class, and
configuration. Two results with the same fingerprint describe the same
experiment; differing fingerprints mean the results are not duplicates.

Fingerprints are NOT cryptographic attestations. They detect accidental
duplicates and support regression baselines; they do not prove that a
result was produced by a trusted process.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

_FINGERPRINT_FIELDS = (
    ("schema_version", None),
    ("model.name", None),
    ("model.checksum", None),
    ("model.format", None),
    ("model.quantization", None),
    ("runtime.name", None),
    ("runtime.backend", None),
    ("runtime.device", None),
    ("reproducibility.workload_type", "llm-generation"),
    ("reproducibility.prompt", None),
    ("reproducibility.max_tokens", None),
    ("reproducibility.temperature", None),
    ("reproducibility.seed", None),
    ("reproducibility.context_length", None),
    ("reproducibility.batch_size", 1),
    ("reproducibility.concurrency", 1),
    ("system.cpu", None),
    ("system.gpu", None),
)


def _get(data: dict[str, Any], path: str) -> Any:
    value: Any = data
    for part in path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
        if value is None:
            return None
    return value


def result_fingerprint(result: dict[str, Any]) -> str:
    """Deterministic sha256 fingerprint of a result's experiment identity."""
    payload: dict[str, Any] = {}
    for path, default in _FINGERPRINT_FIELDS:
        value = _get(result, path)
        payload[path] = default if value is None else value
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def find_duplicates(results: list[dict[str, Any]]) -> list[list[str]]:
    """Group results by fingerprint; return groups with more than one run."""
    groups: dict[str, list[str]] = {}
    for r in results:
        run_id = r.get("run_id") or "<unknown>"
        fp = result_fingerprint(r)
        groups.setdefault(fp, []).append(run_id)
    return [ids for ids in groups.values() if len(ids) > 1]
