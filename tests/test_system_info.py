"""Tests for system detection (sanitization and structure)."""

import re

from benchmark.system_info import detect_system

# Patterns that must never appear in sanitized output.
_FORBIDDEN_PATTERNS = [
    r"[0-9A-F]{2}(:[0-9A-F]{2}){5}",          # MAC addresses
    r"C:\\Users\\[a-zA-Z]",                    # home directory paths
    r"/home/[a-zA-Z]",                         # unix home paths
    r"(?i)serial",                             # serial numbers
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


def test_parse_linux_cpuinfo_single_socket_hyperthreaded():
    from benchmark.system_info import _parse_linux_cpuinfo

    content = """
processor	: 0
model name	: AMD Ryzen 7 7800X3D 8-Core Processor
physical id	: 0
core id		: 0

processor	: 1
model name	: AMD Ryzen 7 7800X3D 8-Core Processor
physical id	: 0
core id		: 0

processor	: 2
model name	: AMD Ryzen 7 7800X3D 8-Core Processor
physical id	: 0
core id		: 1

processor	: 3
model name	: AMD Ryzen 7 7800X3D 8-Core Processor
physical id	: 0
core id		: 1
"""
    cpu, cores_physical = _parse_linux_cpuinfo(content)
    assert cpu == "AMD Ryzen 7 7800X3D 8-Core Processor"
    assert cores_physical == 2


def test_parse_linux_cpuinfo_dual_socket():
    from benchmark.system_info import _parse_linux_cpuinfo

    content = """
processor	: 0
model name	: Intel(R) Xeon(R) CPU E5-2680 v4 @ 2.40GHz
physical id	: 0
core id		: 0

processor	: 1
model name	: Intel(R) Xeon(R) CPU E5-2680 v4 @ 2.40GHz
physical id	: 1
core id		: 0
"""
    cpu, cores_physical = _parse_linux_cpuinfo(content)
    assert cpu == "Intel(R) Xeon(R) CPU E5-2680 v4 @ 2.40GHz"
    assert cores_physical == 2

