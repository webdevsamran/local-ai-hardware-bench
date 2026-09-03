"""Cross-platform hardware and OS detection.

Detection is read-only and sanitized: no serial numbers, MAC addresses,
usernames, home-directory paths, or other confidential identifiers are
ever collected. Values that cannot be determined are reported as None
rather than guessed.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import platform
import re
import subprocess
from typing import Any

_KNOWN_NPU_PATTERNS = [
    r"Intel\(R\) AI Boost",
    r"AMD Ryzen AI",
    r"AMD AIE",
    r"XDNA",
    r"Qualcomm Hexagon",
    r"Hexagon NPU",
    r"Apple Neural Engine",
]


def _run(cmd: list[str], timeout: float = 10.0) -> str | None:
    """Run a command and return stdout, or None if it fails."""
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        if proc.returncode == 0:
            return proc.stdout.strip()
        return None
    except (OSError, subprocess.TimeoutExpired):
        return None


def get_os_info() -> dict[str, Any]:
    """Return operating system name and version."""
    system = platform.system()
    if system == "Windows":
        version = platform.version()  # e.g. 10.0.26200
        release = platform.release()
        return {"os": f"Windows {release}", "os_version": version}
    if system == "Linux":
        kernel = platform.release()
        return {"os": "Linux", "os_version": kernel}
    if system == "Darwin":
        return {"os": "macOS", "os_version": platform.mac_ver()[0]}
    return {"os": system, "os_version": platform.version()}


def _windows_total_ram_gb() -> float | None:
    """Total physical RAM in GB via GlobalMemoryStatusEx (no deps)."""

    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.wintypes.DWORD),
            ("dwMemoryLoad", ctypes.wintypes.DWORD),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    stat = MEMORYSTATUSEX()
    stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    try:
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
        total_bytes = float(stat.ullTotalPhys)
        return round(total_bytes / (1024**3), 1)
    except OSError:
        return None


def _linux_total_ram_gb() -> float | None:
    meminfo = "/proc/meminfo"
    try:
        with open(meminfo, encoding="ascii") as fh:
            for line in fh:
                if line.startswith("MemTotal:"):
                    kb = int(line.split()[1])
                    return round(kb / (1024 * 1024), 1)
    except OSError:
        pass
    return None


def _darwin_total_ram_gb() -> float | None:
    """Total physical RAM in GB via sysctl hw.memsize (no deps)."""
    out = _run(["sysctl", "-n", "hw.memsize"])
    if out:
        try:
            return round(int(out.strip()) / (1024**3), 1)
        except ValueError:
            return None
    return None


def get_ram_gb() -> float | None:
    """Total physical RAM in GB."""
    system = platform.system()
    if system == "Windows":
        return _windows_total_ram_gb()
    if system == "Linux":
        return _linux_total_ram_gb()
    if system == "Darwin":
        return _darwin_total_ram_gb()
    return None


def get_cpu_info() -> dict[str, Any]:
    """CPU model and core counts."""
    info: dict[str, Any] = {
        "cpu": None,
        "cpu_cores_physical": None,
        "cpu_cores_logical": None,
    }
    logical = __import__("os").cpu_count()
    info["cpu_cores_logical"] = logical

    system = platform.system()
    if system == "Windows":
        # Registry read avoids spawning PowerShell; fast and dependency-free.
        try:
            import winreg

            key_path = r"HARDWARE\DESCRIPTION\System\CentralProcessor\0"
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
                info["cpu"] = winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()
        except OSError:
            info["cpu"] = platform.processor() or None
        cores = _run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "(Get-CimInstance Win32_Processor).NumberOfCores",
            ]
        )
        if cores and cores.strip().isdigit():
            info["cpu_cores_physical"] = int(cores.strip())
    elif system == "Linux":
        cpuinfo = "/proc/cpuinfo"
        names: list[str] = []
        # Unique (physical id, core id) pairs = physical cores.
        core_pairs: set[tuple[str, str]] = set()
        current: dict[str, str] = {}
        try:
            with open(cpuinfo, encoding="ascii") as fh:
                for line in fh:
                    if line.startswith("model name"):
                        names.append(line.split(":", 1)[1].strip())
                    elif line.startswith("physical id"):
                        current["physical"] = line.split(":", 1)[1].strip()
                    elif line.startswith("core id"):
                        current["core"] = line.split(":", 1)[1].strip()
                    elif not line.strip() and current:
                        if "physical" in current and "core" in current:
                            core_pairs.add((current["physical"], current["core"]))
                        current = {}
        except OSError:
            pass
        if current and "physical" in current and "core" in current:
            core_pairs.add((current["physical"], current["core"]))
        if names:
            info["cpu"] = names[0]
        if core_pairs:
            info["cpu_cores_physical"] = len(core_pairs)
    elif system == "Darwin":
        # Apple Silicon / Intel Macs expose identity and topology via sysctl.
        brand = _run(["sysctl", "-n", "machdep.cpu.brand_string"])
        if brand and brand.strip():
            info["cpu"] = brand.strip()
        else:
            info["cpu"] = platform.processor() or None
        physical = _run(["sysctl", "-n", "hw.physicalcpu"])
        if physical and physical.strip().isdigit():
            info["cpu_cores_physical"] = int(physical.strip())
        logical = _run(["sysctl", "-n", "hw.logicalcpu"])
        if logical and logical.strip().isdigit():
            info["cpu_cores_logical"] = int(logical.strip())
    else:
        info["cpu"] = platform.processor() or None
    return info


def get_nvidia_gpus() -> list[dict[str, Any]]:
    """Query NVIDIA GPUs via nvidia-smi. Returns [] when unavailable.

    Each entry includes device index and PCIe link info where the driver
    exposes it; unavailable fields stay None (#28, #29).
    """
    out = _run(
        [
            "nvidia-smi",
            "--query-gpu=index,name,memory.total,driver_version,compute_cap,"
            "pci.pcie_gen.current,pci.pcie_link.width.current",
            "--format=csv,noheader,nounits",
        ]
    )
    gpus: list[dict[str, Any]] = []
    if not out:
        return gpus
    for line in out.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 4:
            continue
        # Older drivers may not support the extended query; fall back.
        if len(parts) >= 7:
            index_s, name, vram_mb, driver, compute_cap, pcie_gen, pcie_width = parts[:7]
        else:
            name, vram_mb, driver, compute_cap = parts[:4]
            index_s = pcie_gen = pcie_width = ""
        gpu: dict[str, Any] = {
            "vendor": "NVIDIA",
            "name": name,
            "driver_version": driver,
            "vram_mb": int(vram_mb) if vram_mb.isdigit() else None,
            "index": int(index_s) if index_s.isdigit() else None,
            "pcie_gen": int(pcie_gen) if pcie_gen.isdigit() else None,
            "pcie_width": int(pcie_width.replace("x", "")) if pcie_width.strip() else None,
        }
        try:
            major, minor = compute_cap.split(".")
            gpu["compute_capability"] = f"{int(major)}.{int(minor)}"
        except ValueError:
            pass
        gpus.append(gpu)
    return gpus


def get_gpu_info() -> dict[str, Any]:
    """Primary GPU summary for result documents."""
    nvidia = get_nvidia_gpus()
    if nvidia:
        primary = nvidia[0]
        return {
            "gpu": primary["name"],
            "gpu_vram_mb": primary.get("vram_mb"),
            "gpu_driver_version": primary.get("driver_version"),
        }
    # Fall back to WMI on Windows (reports iGPU or unknown VRAM).
    if platform.system() == "Windows":
        out = _run(
            ["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_VideoController).Name"]
        )
        if out:
            names = [n.strip() for n in out.splitlines() if n.strip()]
            if names:
                return {"gpu": names[0], "gpu_vram_mb": None}
    return {"gpu": None, "gpu_vram_mb": None}


def get_npu_info() -> str | None:
    """Detect known NPUs via Plug-and-Play device enumeration (Windows)."""
    if platform.system() != "Windows":
        return None
    out = _run(["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_PnPEntity).Name"])
    if not out:
        return None
    for pattern in _KNOWN_NPU_PATTERNS:
        if re.search(pattern, out, re.IGNORECASE):
            match = re.search(pattern, out, re.IGNORECASE)
            assert match is not None
            return match.group(0)
    return None


def get_platform_name() -> str | None:
    """Best-effort machine product name (sanitized; no serials)."""
    system = platform.system()
    if system == "Windows":
        out = _run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "(Get-CimInstance Win32_ComputerSystemProduct).Name",
            ]
        )
        if out:
            return out.strip().splitlines()[0]
    elif system == "Linux":
        try:
            with open("/sys/devices/virtual/dmi/id/product_name", encoding="utf-8") as fh:
                return fh.read().strip()
        except OSError:
            pass
    return None


def get_topology() -> dict[str, Any]:
    """Hardware topology facts: NUMA, sockets, GPU count, unified memory,
    CPU instruction-set features. Unavailable facts are None (#28, #30).

    No serial numbers or PII: only structural counts and feature names.
    """
    topo: dict[str, Any] = {
        "numa_nodes": None,
        "sockets": None,
        "unified_memory": None,
        "cpu_features": [],
        "gpu_count": None,
    }
    system = platform.system()
    if system == "Linux":
        import os as _os

        try:
            topo["numa_nodes"] = (
                len([d for d in _os.listdir("/sys/devices/system/node") if d.startswith("node")])
                or None
            )
        except OSError:
            pass
        socket_ids: set[str] = set()
        try:
            with open("/proc/cpuinfo", encoding="ascii") as fh:
                for line in fh:
                    if line.startswith("physical id"):
                        socket_ids.add(line.split(":", 1)[1].strip())
                    elif line.startswith("flags"):
                        topo["cpu_features"] = sorted(set(line.split(":", 1)[1].split()))
        except OSError:
            pass
        if socket_ids:
            topo["sockets"] = len(socket_ids)
    elif system == "Windows":
        out = _run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "(Get-CimInstance Win32_Processor | Measure-Object -Property DeviceID).Count",
            ]
        )
        if out and out.strip().isdigit():
            topo["sockets"] = int(out.strip())
    elif system == "Darwin":
        # Apple Silicon has unified memory; Intel Macs do not.
        topo["unified_memory"] = platform.machine() == "arm64"
    gpus = get_nvidia_gpus()
    if gpus:
        topo["gpu_count"] = len(gpus)
    return topo


def detect_system() -> dict[str, Any]:
    """Full sanitized system description used in every benchmark result."""
    os_info = get_os_info()
    cpu = get_cpu_info()
    gpu = get_gpu_info()
    ram = get_ram_gb()
    npu = get_npu_info()
    topology = get_topology()
    nvidia_gpus = get_nvidia_gpus()
    result: dict[str, Any] = {
        "os": os_info["os"],
        "os_version": os_info["os_version"],
        "cpu": cpu["cpu"],
        "cpu_cores_physical": cpu["cpu_cores_physical"],
        "cpu_cores_logical": cpu["cpu_cores_logical"],
        "gpu": gpu["gpu"],
        "gpu_vram_mb": gpu["gpu_vram_mb"],
        "gpu_driver_version": gpu.get("gpu_driver_version"),
        "npu": npu,
        "ram_gb": ram,
        "platform_name": get_platform_name(),
        "topology": topology,
    }
    # Multi-GPU representation (#29): every detected accelerator separately.
    if nvidia_gpus:
        result["gpus"] = nvidia_gpus
    return result
