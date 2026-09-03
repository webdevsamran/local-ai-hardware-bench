"""Formal JSON Schema validation for result documents (#22).

Semantic checks live in :mod:`aihwbench.schemas`; this module adds
version-specific *formal* JSON Schema validation so contract drift
(unknown blocks, wrong types on known fields) is caught independently
of the hand-written semantic rules.

Formal schemas ship in ``schemas/``:

- ``result-1.0.schema.json`` — published schema 1.0 documents
- ``result-2.0.schema.json`` — schema 2.0 (protocol/workload versions)

Requires the optional ``jsonschema`` package. ``validate_formal``
fails closed: when the validator is unavailable it raises instead of
returning an empty pass list, so CI callers treat that as an
environment error rather than a silent validation success.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

__all__ = ["FORMAL_VERSIONS", "load_formal_schema", "validate_formal"]

_SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schemas"
_FILES = {"1.0": "result-1.0.schema.json", "2.0": "result-2.0.schema.json"}
FORMAL_VERSIONS = tuple(_FILES)


def load_formal_schema(version: str) -> dict[str, Any]:
    """Load one versioned formal schema by schema_version string."""
    name = _FILES.get(version)
    if name is None:
        raise ValueError(
            f"no formal schema for version {version!r}; known: {', '.join(FORMAL_VERSIONS)}"
        )
    path = _SCHEMA_DIR / name
    if not path.is_file():
        raise FileNotFoundError(f"formal schema missing: {path}")
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def validate_formal(doc: dict[str, Any], version: str | None = None) -> list[str]:
    """Validate a result document formally; returns human-readable errors.

    ``version`` defaults to the document's own ``schema_version``. The
    returned list is empty only when the document truly validates.
    """
    try:
        import jsonschema
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise RuntimeError(
            "formal validation requires jsonschema (pip install jsonschema)"
        ) from exc
    v = version or str(doc.get("schema_version") or "")
    schema = load_formal_schema(v)
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(doc), key=lambda e: list(e.absolute_path))
    out: list[str] = []
    for err in errors:
        loc = "$." + ".".join(str(p) for p in err.absolute_path) if err.absolute_path else "$"
        out.append(f"{loc}: {err.message}")
    return out
