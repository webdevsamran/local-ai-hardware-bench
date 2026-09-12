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
    "pattern_registry",
    "redact_match",
    "redact_object",
    "redact_text",
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
    # Cloud access-key ids. The prefixes are assigned by AWS and are not
    # something that occurs in a benchmark result by accident, so matching them
    # cannot redact legitimate content.
    (
        "cloud_access_key",
        "cloud access key id",
        re.compile(r"\b(?:AKIA|ASIA|AROA|AIDA|ANPA|ANVA|AIPA)[0-9A-Z]{12,}\b"),
    ),
    # Provider API keys with a distinctive prefix. Deliberately narrow: a bare
    # high-entropy string is indistinguishable from a checksum, and this
    # project puts SHA-256 digests in every result.
    (
        "api_key",
        "API key",
        re.compile(r"\b(?:sk|pk|rk)-[A-Za-z0-9_-]{16,}\b"),
    ),
    # Windows user directories, with either separator.
    #
    # The original pattern required backslashes, which missed the form this
    # project produces constantly: Windows accepts `/` everywhere, `pathlib`
    # emits it, JSON carries it without escaping, and `C:/Users/name/models`
    # therefore passed the privacy scan and would have been published. A
    # result file is a public artifact here, so that is a leak rather than an
    # inconvenience.
    #
    # ``[\\/]+`` also matches repr-doubled backslashes, so a value that was
    # repr()'d before landing in the document is still caught.
    (
        "windows_path",
        "Windows user home path",
        re.compile(r"[A-Za-z]:[\\/]+Users[\\/]+[^\"'\\/\s]+", re.IGNORECASE),
    ),
    (
        "home_path",
        "home directory",
        re.compile(r"(?:[\\/]{1,2})home(?:[\\/]{1,2})[A-Za-z0-9._-]+", re.IGNORECASE),
    ),
    # macOS home directories, which were not covered at all: the pattern above
    # matches `/home/`, and macOS uses `/Users/`. Every result from a Mac
    # carried its owner's username past the scan -- and this project ships an
    # MLX backend whose entire audience is on macOS.
    #
    # Anchored to the start of a path segment so `.../Users/` inside some
    # unrelated string is still caught, while the bare word "Users" is not.
    (
        "macos_home_path",
        "macOS home directory",
        re.compile(r"(?<![A-Za-z0-9]):?[\\/]Users[\\/][^\"'\\/\s]+"),
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


def pattern_registry() -> list[dict[str, Any]]:
    """The pattern registry in a serializable form.

    Published so the dashboard can run the same privacy scan in the browser
    rather than carrying a second, hand-written copy of these expressions.
    A submission page that scanned with its own patterns would eventually
    disagree with the CLI about whether a file is safe to share, and the
    direction of that disagreement is not one anyone would notice until a
    leak had already been published.

    The expressions are deliberately kept within the syntax JavaScript's
    RegExp also understands -- no lookbehind, no named groups, no possessive
    quantifiers -- so this stays a transcription rather than a translation.
    Reference vectors generated alongside pin that the two engines agree.
    """
    return [
        {
            "id": pattern_id,
            "label": label,
            "pattern": pattern.pattern,
            # Only IGNORECASE is used, and it is the one flag whose meaning is
            # identical in both engines.
            "ignore_case": bool(pattern.flags & re.IGNORECASE),
        }
        for pattern_id, label, pattern in _PATTERNS
    ]


_REDACT_KEEP = 4


def redact_match(value: str, keep: int = _REDACT_KEEP) -> str:
    """Redact a matched value: short prefix + length, never the full text."""
    if len(value) <= keep:
        return f"[redacted len={len(value)}]"
    return f"{value[:keep]}...[redacted len={len(value)}]"


def redact_text(text: str) -> str:
    """Replace every occurrence of every pattern with an inert placeholder.

    Unlike :func:`redact_match`, which keeps a short prefix so a CI finding is
    recognisable, this keeps *nothing* of the matched value: the output is
    published data, and a four-character prefix of a leak is still a leak.
    The placeholder names the pattern instead, so a reader can tell what was
    removed without seeing any of it.

    Every match is replaced, not just the first -- ``_scan_text`` reports one
    finding per pattern per string because that is enough to fail CI, but
    scrubbing must remove all of them.
    """
    for pattern_id, _, pattern in _PATTERNS:
        text = pattern.sub(f"[redacted:{pattern_id}]", text)
    return text


def redact_object(data: Any) -> Any:
    """Return a copy of ``data`` with every detected identifier removed.

    Detection alone cannot protect a published dataset: a leak in a submitted
    result has to be *removed*, and a single leak in public data is
    unrecoverable. This is the counterpart to :func:`scan_object` -- the same
    pattern registry, applied as a rewrite instead of a report.

    Dictionary keys are scrubbed as well as values, because the scanner
    inspects keys too. When two distinct keys scrub to the same string the
    later one is suffixed rather than dropped: silently losing a field would
    be a worse failure than an ugly key.

    Scalars other than strings pass through untouched, and the result is
    idempotent -- scanning it yields no findings.
    """
    if isinstance(data, dict):
        cleaned: dict[Any, Any] = {}
        for key, value in data.items():
            new_key = redact_text(key) if isinstance(key, str) else key
            if new_key in cleaned:
                suffix = 2
                while f"{new_key}#{suffix}" in cleaned:
                    suffix += 1
                new_key = f"{new_key}#{suffix}"
            cleaned[new_key] = redact_object(value)
        return cleaned
    if isinstance(data, list):
        return [redact_object(item) for item in data]
    if isinstance(data, tuple):
        return tuple(redact_object(item) for item in data)
    if isinstance(data, str):
        return redact_text(data)
    return data


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
