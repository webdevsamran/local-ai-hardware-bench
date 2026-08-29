"""Tests for system detection (sanitization and structure)."""

import re

from aihwbench.system_info import detect_system

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


# --- Issue #24: macOS (Darwin) CPU identity/topology and RAM detection ---


def test_darwin_ram_and_cpu_detection(monkeypatch):
    import aihwbench.system_info as si

    monkeypatch.setattr(si.platform, "system", lambda: "Darwin")

    def fake_run(cmd, timeout=10.0):
        table = {
            ("sysctl", "-n", "hw.memsize"): "34359738368",
            ("sysctl", "-n", "machdep.cpu.brand_string"): "Apple M2 Pro",
            ("sysctl", "-n", "hw.physicalcpu"): "10",
            ("sysctl", "-n", "hw.logicalcpu"): "10",
        }
        return table.get(tuple(cmd))

    monkeypatch.setattr(si, "_run", fake_run)
    assert si.get_ram_gb() == 32.0
    cpu = si.get_cpu_info()
    assert cpu["cpu"] == "Apple M2 Pro"
    assert cpu["cpu_cores_physical"] == 10
    assert cpu["cpu_cores_logical"] == 10


def test_darwin_missing_sysctl_stays_none(monkeypatch):
    import aihwbench.system_info as si

    monkeypatch.setattr(si.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(si, "_run", lambda cmd, timeout=10.0: None)
    assert si.get_ram_gb() is None  # unavailable stays null, never estimated
