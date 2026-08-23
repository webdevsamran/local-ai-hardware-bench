"""Tests for system detection (sanitization and structure)."""

import re

from benchmark.system_info import detect_system

# Patterns that must never appear in sanitized output.
#
# Note on the serial pattern: the bare word "serial" is allowed because
# modern kernels expose a CPU *capability flag* literally named "serial"
# (e.g. in /proc/cpuinfo on recent Intel Xeon parts). A real leak is a
# serial label followed by an assigned value, matching the semantics of
# benchmark/sanitize.py's SERIAL_RE.
_FORBIDDEN_PATTERNS = [
    r"[0-9A-F]{2}(:[0-9A-F]{2}){5}",  # MAC addresses
    r"C:\\Users\\[a-zA-Z]",  # home directory paths
    r"/home/[a-zA-Z]",  # unix home paths
    r"(?i)serial\s*(?:number|no|#)?\s*[:=]\s*[A-Za-z0-9]+",  # serial values
]


def test_detect_system_structure():
    system = detect_system()
    for key in ("os", "os_version", "cpu", "ram_gb"):
        assert key in system
    assert isinstance(system.get("os"), str) and system["os"]


def test_detect_system_sanitized():
    text = repr(detect_system())
    for pattern in _FORBIDDEN_PATTERNS:
        assert not re.search(pattern, text), f"forbidden pattern leaked: {pattern}"


def test_ram_is_plausible():
    ram = detect_system()["ram_gb"]
    if ram is not None:
        assert 0.5 <= ram <= 8192
