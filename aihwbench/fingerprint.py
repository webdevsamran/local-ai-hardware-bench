"""Deterministic result fingerprints for duplicate detection.

A fingerprint is a stable digest over the *experiment identity* of a
result: protocol/schema versions, model, workload, runtime, hardware, and
configuration. Two results with the same fingerprint describe the same
experiment and are legitimate repeats; differing fingerprints mean the
results are not duplicates.

Identity vs. integrity: a fingerprint identifies *what was measured*
(experiment identity). It is deliberately NOT an artifact-integrity hash
— result/provenance hashes (``provenance.result_hash``) cover *whether
the artifact bytes were altered*. Neither proves a result was produced by
a trusted process.

The algorithm is versioned via ``FINGERPRINT_ALGORITHM_VERSION``, embedded
in every digest so stored fingerprints remain interpretable when the
field set evolves.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

FINGERPRINT_ALGORITHM_VERSION = 2

_FINGERPRINT_FIELDS = (
    ("fingerprint_algorithm_version", None),
    # Protocol / contract identity
    ("schema_version", None),
    ("protocol_version", None),
    # Model identity
    ("model.name", None),
    ("model.checksum", None),
    ("model.format", None),
    ("model.quantization", None),
    # Runtime identity
    ("runtime.name", None),
    ("runtime.backend", None),
    ("runtime.version", None),
    ("runtime.device", None),
    # Workload identity (typed block and legacy reproducibility fields)
    ("workload.id", None),
    ("workload.kind", None),
    ("workload.version", None),
    ("reproducibility.workload_type", "llm-generation"),
    ("reproducibility.prompt", None),
    ("reproducibility.max_tokens", None),
    ("reproducibility.temperature", None),
    ("reproducibility.seed", None),
    ("reproducibility.context_length", None),
    ("reproducibility.batch_size", 1),
    ("reproducibility.concurrency", 1),
    # Hardware identity (CPU/GPU strings plus OS and RAM so two distinct
    # machines with identical CPU model strings do not merge)
    ("system.cpu", None),
    ("system.gpu", None),
    ("system.os", None),
    ("system.ram_gb", None),
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
    """Deterministic sha256 fingerprint of a result's experiment identity.

    The digest covers ``FINGERPRINT_ALGORITHM_VERSION`` and every field in
    ``_FINGERPRINT_FIELDS`` (absent fields normalize to ``None``, so results
    from both older and newer writers compare consistently). Field values
    are taken positionally, never by dict order, making the output stable
    across JSON key ordering.
    """
    payload: dict[str, Any] = {"fingerprint_algorithm_version": FINGERPRINT_ALGORITHM_VERSION}
    for path, default in _FINGERPRINT_FIELDS:
        if path == "fingerprint_algorithm_version":
            continue
        value = _get(result, path)
        payload[path] = default if value is None else value
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def find_duplicates(results: list[dict[str, Any]]) -> list[list[str]]:
    """Group results by fingerprint; return groups with more than one run.

    Groups are computed under the current ``FINGERPRINT_ALGORITHM_VERSION``;
    fingerprints stored by older algorithm versions are not comparable and
    must be recomputed before dedup decisions.
    """
    groups: dict[str, list[str]] = {}
    for r in results:
        run_id = r.get("run_id") or "<unknown>"
        fp = result_fingerprint(r)
        groups.setdefault(fp, []).append(run_id)
    return [ids for ids in groups.values() if len(ids) > 1]
