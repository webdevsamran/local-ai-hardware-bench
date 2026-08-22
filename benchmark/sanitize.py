"""Privacy sanitization and detection for benchmark artifacts.

Detection output from `aihwbench` is sanitized by design. Before any
result is published, this module scans for accidental exposure of
confidential identifiers. The scan fails closed: any match is reported.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

MAC_RE = re.compile(r"(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}", re.IGNORECASE)
IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
IPV6_RE = re.compile(r"\b(?:[0-9A-Fa-f]{1,4}:){2,7}[0-9A-Fa-f]{0,4}\b")
SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
USERNAME_RE = re.compile(r"\bUSERNAME\b", re.IGNORECASE)
TOKEN_RE = re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}\b|Bearer\s+[A-Za-z0-9._~+/=-]{10,})")

WINDOWS_USER_RE = re.compile(r"[A-Za-z]:\\\\Users\\\\[^\\\\\"']+", re.IGNORECASE)
HOME_DIR_RE = re.compile(r"\\\\home\\\\[^\\\\/]+", re.IGNORECASE)
SERIAL_RE = re.compile(r"\bserial\s*(?:number|no|#)?\s*[:=]\s*[A-Za-z0-9]+", re.IGNORECASE)


def _scan_text(text: str) -> tuple[bool, list[str]]:
    """Scan a text blob; returns (clean, list of findings)."""
    findings: list[str] = []

    def check(pattern: re.Pattern[str], label: str) -> None:
        for match in pattern.finditer(text):
            findings.append(f"{label}: {match.group(0)!r}")

    check(MAC_RE, "MAC address")
    check(IPV4_RE, "IPv4 address")
    check(IPV6_RE, "IPv6 address")
    check(SSN_RE, "SSN")
    check(TOKEN_RE, "possible token/credential")
    check(WINDOWS_USER_RE, "Windows user home path")
    check(HOME_DIR_RE, "home directory")
    check(SERIAL_RE, "serial number")
    check(USERNAME_RE, "username placeholder")

    return (len(findings) == 0, findings)


def scan_object(data: Any) -> tuple[bool, list[str]]:
    """Recursively convert an object to text and scan it."""
    if isinstance(data, dict):
        items = [f"{k}={v}" for k, v in data.items()]
        text = ", ".join(items)
    elif isinstance(data, list):
        text = str(data)
    elif data is None:
        return True, []
    else:
        text = str(data)
    return _scan_text(text)


def scan_file(path: Path) -> tuple[bool, list[str]]:
    """Scan a result JSON file for private identifiers."""
    text = path.read_text(encoding="utf-8")
    return _scan_text(text)
