"""Privacy sanitization and detection for benchmark artifacts.

Canonical recursive structured privacy scanner — the single source of
truth for privacy detection semantics. ``aihwbench.quality`` delegates
its privacy check here, and CI fails closed on any finding.

Design:

- Scanning walks the object structure and reports a JSON-style path
  (``$.metrics.notes[0]``) per finding instead of flattening the object
  to text first, so leaks hidden in nested dicts/lists keep their
  structural context and nothing is lost to ``repr()`` artifacts.
- Findings never echo the full matched value: only a short prefix plus
  the matched length is shown, so CI logs cannot leak secrets.
- The scan fails closed: any match is reported as a finding.
- Detection is regex-based and platform-independent: Windows and POSIX
  user paths are detected on every operating system.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

__all__ = [
    "PATTERN_IDS",
    "redact_match",
    "scan_file",
    "scan_object",
    "scan_object_detailed",
]

# Canonical pattern registry: (pattern_id, human label, compiled regex).
# Tuple order defines deterministic finding order. ``aihwbench.quality``
# reports these ids in its ``privacy_hits`` check.
_PATTERNS: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    (
        "mac_address",
        "MAC address",
        re.compile(r"(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}"),
    ),
    (
        "ipv4",
        "IPv4 address",
        re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    ),
    (
        "ipv6",
        "IPv6 address",
        re.compile(r"\b(?:[0-9A-Fa-f]{1,4}:){2,7}[0-9A-Fa-f]{0,4}\b"),
    ),
    ("ssn", "SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    (
        "token_or_credential",
        "possible token/credential",
        re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}\b|Bearer\s+[A-Za-z0-9._~+/=-]{10,})"),
    ),
    # ``\\+`` (one-or-more literal backslashes) also matches repr-doubled
    # text, so leaks are caught even if a value was repr()'d first.
    (
        "windows_path",
        "Windows user home path",
        re.compile(r"[A-Za-z]:\\+Users\\+[^\"'\\]+", re.IGNORECASE),
    ),
    (
        "home_path",
        "home directory",
        re.compile(r"(?:[\\/]{1,2})home(?:[\\/]{1,2})[A-Za-z0-9._-]+", re.IGNORECASE),
    ),
    (
        "serial_number",
        "serial number",
        re.compile(r"\bserial\s*(?:number|no|#)?\s*[:=]\s*[A-Za-z0-9]+", re.IGNORECASE),
    ),
    (
        "serial_like",
        "serial-like identifier",
        re.compile(r"\bSN[-:]?\s?[0-9A-Z]{8,}\b"),
    ),
    (
        "username_placeholder",
        "username placeholder",
        re.compile(r"\bUSERNAME\b", re.IGNORECASE),
    ),
    (
        "email",
        "email address",
        re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    ),
)

PATTERN_IDS: tuple[str, ...] = tuple(pattern_id for pattern_id, _, _ in _PATTERNS)

_REDACT_KEEP = 4


def redact_match(value: str, keep: int = _REDACT_KEEP) -> str:
    """Redact a matched value: short prefix + length, never the full text."""
    if len(value) <= keep:
        return f"[redacted len={len(value)}]"
    return f"{value[:keep]}...[redacted len={len(value)}]"


def _scan_text(text: str, path: str, findings: list[dict[str, Any]]) -> None:
    """Scan one string; at most one finding per pattern per string."""
    for pattern_id, label, pattern in _PATTERNS:
        match = pattern.search(text)
        if match is None:
            continue
        findings.append(
            {
                "pattern": pattern_id,
                "label": label,
                "path": path,
                "redacted": redact_match(match.group(0)),
                "length": len(match.group(0)),
            }
        )


def _walk(value: Any, path: str, findings: list[dict[str, Any]]) -> None:
    """Depth-first walk emitting findings with JSON-style paths."""
    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{path}.{key}" if isinstance(key, str) else path
            if isinstance(key, str):
                _scan_text(key, f"{child}<key>", findings)
            _walk(item, child, findings)
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _walk(item, f"{path}[{index}]", findings)
    elif isinstance(value, str):
        _scan_text(value, path, findings)
    # Numbers, booleans and null are never scanned: they cannot contain
    # identifiers, and float/None repr noise must not create findings.


def scan_object_detailed(data: Any, path: str = "$") -> list[dict[str, Any]]:
    """Recursively scan a JSON-like object; findings carry structured detail.

    Each finding is a dict with ``pattern`` (canonical id), ``label``,
    ``path`` (JSON-style location), ``redacted`` (prefix + length) and
    ``length`` (matched value length).
    """
    findings: list[dict[str, Any]] = []
    _walk(data, path, findings)
    return findings


def _format(item: dict[str, Any]) -> str:
    return f"{item['label']} at {item['path']}: {item['redacted']}"


def scan_object(data: Any, path: str = "$") -> tuple[bool, list[str]]:
    """Recursively scan an object. Returns (clean, findings).

    Back-compat contract used by CI and the public API: ``findings`` is
    a list of human-readable strings and every finding is redacted.
    """
    findings = scan_object_detailed(data, path)
    return (not findings, [_format(item) for item in findings])


def scan_file(path: Path) -> tuple[bool, list[str]]:
    """Scan a result file for private identifiers.

    JSON files are scanned structurally (full object recursion, paths in
    findings); any other text file falls back to a raw-text scan, which
    is also redacted.
    """
    text = path.read_text(encoding="utf-8")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        findings: list[dict[str, Any]] = []
        _scan_text(text, "$text", findings)
        return (not findings, [_format(item) for item in findings])
    return scan_object(data)
