"""Background telemetry sampling during benchmark runs.

Samples system RAM, GPU memory/utilization/temperature/power while a
benchmark executes. Metrics that cannot be measured on the current
platform are reported as None — never estimated.
"""

from __future__ import annotations

import subprocess
import threading
import time
from collections.abc import Callable
from typing import Any


def _nvidia_smi_sample() -> dict[str, float | None] | None:
    """One sample of GPU telemetry via nvidia-smi. None if unavailable."""
    cmd = [
        "nvidia-smi",
        "--query-gpu=memory.used,utilization.gpu,temperature.gpu,power.draw",
        "--format=csv,noheader,nounits",
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=5.0,
            encoding="utf-8",
            errors="replace",
        )
        if proc.returncode != 0:
            return None
        parts = [p.strip() for p in proc.stdout.strip().splitlines()[0].split(",")]
        if len(parts) < 4:
            return None
        vram_mb, gpu_util, temp_c, power_w = parts[:4]

        def _num(value: str) -> float | None:
            try:
                return float(value)
            except ValueError:
                return None

        return {
            "vram_mb": _num(vram_mb),
            "gpu_util_percent": _num(gpu_util),
            "temperature_c": _num(temp_c),
            "power_watts": _num(power_w),
        }
    except (OSError, subprocess.TimeoutExpired, IndexError):
        return None


def _system_ram_mb() -> float | None:
    """Available-system view: used RAM in MB. Uses psutil when present."""
    try:
        import psutil  # type: ignore[import-untyped]

        vm = psutil.virtual_memory()
        return vm.total / (1024 * 1024) - vm.available / (1024 * 1024)
    except ImportError:
        pass
    # Fallback: Windows GlobalMemoryStatusEx
    try:
        import ctypes
        import ctypes.wintypes

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
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
        return (stat.ullTotalPhys - stat.ullAvailPhys) / (1024 * 1024)
    except OSError:
        return None


def _cpu_util_percent() -> float | None:
    try:
        import psutil

        return psutil.cpu_percent(interval=None)
    except ImportError:
        return None


class TelemetrySampler:
    """Sample hardware telemetry at a fixed interval in a daemon thread."""

    def __init__(self, interval_seconds: float = 0.5) -> None:
        self.interval = interval_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._samples: list[dict[str, float | None]] = []

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self.interval * 4 + 2)

    def summary(self) -> dict[str, Any]:
        """Aggregate collected samples into peak/average metrics."""
        with self._lock:
            samples = list(self._samples)
        if not samples:
            return {
                "peak_ram_mb": None,
                "peak_vram_mb": None,
                "avg_cpu_util_percent": None,
                "avg_gpu_util_percent": None,
                "max_temperature_c": None,
                "average_power_watts": None,
            }

        def peak(key: str) -> float | None:
            values = [float(v) for s in samples if (v := s.get(key)) is not None]
            return max(values) if values else None

        def avg(key: str) -> float | None:
            values = [float(v) for s in samples if (v := s.get(key)) is not None]
            return round(sum(values) / len(values), 2) if values else None

        return {
            "peak_ram_mb": peak("ram_mb"),
            "peak_vram_mb": peak("vram_mb"),
            "avg_cpu_util_percent": avg("cpu_util_percent"),
            "avg_gpu_util_percent": avg("gpu_util_percent"),
            "max_temperature_c": peak("temperature_c"),
            "average_power_watts": avg("power_watts"),
        }

    def _loop(self) -> None:
        while not self._stop.is_set():
            sample: dict[str, float | None] = {
                "ram_mb": _system_ram_mb(),
                "cpu_util_percent": _cpu_util_percent(),
                "vram_mb": None,
                "gpu_util_percent": None,
                "temperature_c": None,
                "power_watts": None,
            }
            gpu = _nvidia_smi_sample()
            if gpu:
                sample.update(gpu)
            with self._lock:
                self._samples.append(sample)
            time.sleep(self.interval)


def measure(fn: Callable[[], Any]) -> tuple[Any, float]:
    """Run fn and return (result, elapsed_ms)."""
    start = time.perf_counter()
    result = fn()
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    return result, elapsed_ms
