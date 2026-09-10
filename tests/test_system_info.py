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


# --- GPU identity must not depend on optional PCIe fields -------------------
#
# Regression tests for a defect found on real hardware: GPU identity and PCIe
# link were queried in one nvidia-smi call, using a field name
# (`pci.pcie_gen.current`) that nvidia-smi does not accept. nvidia-smi fails
# the *whole* query on one unrecognised field, so identity detection returned
# nothing and the Windows WMI fallback reported the integrated GPU -- on a
# machine with an RTX 3080 Ti. The published result then recorded discrete-GPU
# power and VRAM telemetry against an Intel iGPU.
#
# `system.gpu` is in the comparison-safety classifier's strict set, so a wrong
# value there makes runs from two machines look like runs from one. These tests
# pin the property that matters: identity survives *any* failure of the
# optional query.


def _nvidia_smi_query(cmd: list[str]) -> str | None:
    """The `--query-gpu=` field list from an nvidia-smi command, if it is one."""
    if not cmd or cmd[0] != "nvidia-smi":
        return None
    for arg in cmd:
        if arg.startswith("--query-gpu="):
            return arg[len("--query-gpu=") :]
    return None


def test_gpu_identity_survives_a_failing_pcie_query(monkeypatch):
    """An unrecognised PCIe field must cost the link data, never the GPU."""
    import aihwbench.system_info as si

    def fake_run(cmd, timeout=10.0):
        query = _nvidia_smi_query(cmd)
        if query is None:
            return None
        if "pcie" in query:
            # What nvidia-smi does when a field name is not recognised.
            return None
        return "0, NVIDIA GeForce RTX 3080 Ti Laptop GPU, 16384, 610.74, 8.6"

    monkeypatch.setattr(si, "_run", fake_run)
    gpus = si.get_nvidia_gpus()
    assert len(gpus) == 1
    assert gpus[0]["name"] == "NVIDIA GeForce RTX 3080 Ti Laptop GPU"
    assert gpus[0]["vram_mb"] == 16384
    assert gpus[0]["compute_capability"] == "8.6"
    # The optional data is absent, not fabricated.
    assert gpus[0]["pcie_gen"] is None
    assert gpus[0]["pcie_width"] is None


def test_gpu_identity_query_asks_for_no_optional_fields(monkeypatch):
    """Structural guard: identity and PCIe never share a query again.

    Testing the *outcome* above is not enough. Someone appending one more
    convenient field to the identity query reintroduces exactly this defect,
    and every behavioural test still passes as long as that field happens to
    be spelled correctly on the machine running CI.
    """
    import aihwbench.system_info as si

    queries: list[str] = []

    def fake_run(cmd, timeout=10.0):
        query = _nvidia_smi_query(cmd)
        if query is not None:
            queries.append(query)
        return None

    monkeypatch.setattr(si, "_run", fake_run)
    si.get_nvidia_gpus()

    assert queries, "expected at least the identity query"
    identity = queries[0]
    assert identity == "index,name,memory.total,driver_version,compute_cap"


def test_pcie_link_is_attached_when_the_query_succeeds(monkeypatch):
    import aihwbench.system_info as si

    def fake_run(cmd, timeout=10.0):
        query = _nvidia_smi_query(cmd)
        if query is None:
            return None
        if "pcie" in query:
            return "0, 4, 16"
        return "0, NVIDIA GeForce RTX 3080 Ti Laptop GPU, 16384, 610.74, 8.6"

    monkeypatch.setattr(si, "_run", fake_run)
    gpu = si.get_nvidia_gpus()[0]
    assert gpu["pcie_gen"] == 4
    assert gpu["pcie_width"] == 16


def test_pcie_link_records_the_max_not_the_idle_current(monkeypatch):
    """The link the machine has, not the one it happened to be idling at.

    Current link values drop to gen 1 x8 when the GPU is idle to save power,
    so recording them describes the moment of sampling rather than the
    hardware -- and two results from one machine would disagree.
    """
    import aihwbench.system_info as si

    seen: list[str] = []

    def fake_run(cmd, timeout=10.0):
        query = _nvidia_smi_query(cmd)
        if query is None:
            return None
        seen.append(query)
        if "pcie" in query:
            return "0, 4, 16"
        return "0, NVIDIA GeForce RTX 3080 Ti Laptop GPU, 16384, 610.74, 8.6"

    monkeypatch.setattr(si, "_run", fake_run)
    si.get_nvidia_gpus()
    pcie_query = next(q for q in seen if "pcie" in q)
    assert "max" in pcie_query
    assert "current" not in pcie_query


def test_pcie_rows_are_matched_by_index_not_position(monkeypatch):
    """Multi-GPU: nvidia-smi row order is not a contract worth betting on."""
    import aihwbench.system_info as si

    def fake_run(cmd, timeout=10.0):
        query = _nvidia_smi_query(cmd)
        if query is None:
            return None
        if "pcie" in query:
            return "1, 3, 8\n0, 4, 16"  # deliberately reversed
        return (
            "0, NVIDIA GeForce RTX 4090, 24564, 610.74, 8.9\n"
            "1, NVIDIA GeForce RTX 3060, 12288, 610.74, 8.6"
        )

    monkeypatch.setattr(si, "_run", fake_run)
    gpus = {gpu["index"]: gpu for gpu in si.get_nvidia_gpus()}
    assert gpus[0]["pcie_gen"] == 4 and gpus[0]["pcie_width"] == 16
    assert gpus[1]["pcie_gen"] == 3 and gpus[1]["pcie_width"] == 8


def test_wmi_fallback_never_runs_when_an_nvidia_gpu_is_present(monkeypatch):
    """The fallback exists for machines with no NVIDIA GPU, not as a rescue.

    This is the defect's actual damage: the fallback answered confidently with
    the wrong GPU rather than reporting nothing.
    """
    import aihwbench.system_info as si

    monkeypatch.setattr(si.platform, "system", lambda: "Windows")

    def fake_run(cmd, timeout=10.0):
        if cmd and cmd[0] == "powershell":
            raise AssertionError("WMI fallback ran despite a detected NVIDIA GPU")
        query = _nvidia_smi_query(cmd)
        if query is None or "pcie" in query:
            return None
        return "0, NVIDIA GeForce RTX 3080 Ti Laptop GPU, 16384, 610.74, 8.6"

    monkeypatch.setattr(si, "_run", fake_run)
    info = si.get_gpu_info()
    assert info["gpu"] == "NVIDIA GeForce RTX 3080 Ti Laptop GPU"
    assert info["gpu_vram_mb"] == 16384
