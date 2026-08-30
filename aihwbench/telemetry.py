"""Background telemetry sampling during benchmark runs.

Samples system RAM, CPU utilization, and GPU memory/utilization/
temperature/power while a benchmark executes. Metrics that cannot be
measured on the current platform are reported as None — never estimated.

Every sample carries explicit scope/source metadata so consumers can
tell system-wide measurements from per-process ones:

- RAM/CPU are SYSTEM-WIDE (scope ``system``).
- GPU metrics come from the first NVIDIA GPU reported by ``nvidia-smi``
  (scope ``device``) when that tool is present.
"""

from __future__ import annotations

import platform
import subprocess
import threading
import time
from collections.abc import Callable
from typing import Any

__all__ = ["TelemetrySampler", "measure"]


def _nvidia_smi_sample() -> dict[str, Any] | None:
    """One sample of GPU telemetry via nvidia-smi. None if unavailable.

    Queries the device index and name alongside the metrics so results
    state *which* device was measured (audited defect: previously the
    fields could read like generic "the GPU" metrics).
    """
    cmd = [
        "nvidia-smi",
        "--query-gpu=index,name,memory.used,utilization.gpu,temperature.gpu,power.draw",
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
        if len(parts) < 6:
            return None
        device_index, device_name, vram_mb, gpu_util, temp_c, power_w = parts[:6]

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
            "gpu_device_index": device_index,
            "gpu_device_name": device_name or None,
        }
    except (OSError, subprocess.TimeoutExpired, IndexError):
        return None


def _system_ram_sample() -> tuple[float | None, str | None]:
    """Used system RAM in MB as (value, source). Platform-safe fallback."""
    try:
        import psutil  # type: ignore[import-untyped]

        vm = psutil.virtual_memory()
        return (
            vm.total / (1024 * 1024) - vm.available / (1024 * 1024),
            "psutil.virtual_memory",
        )
    except ImportError:
        pass
    # Fallback: Windows GlobalMemoryStatusEx. Guarded by platform so the
    # ctypes.windll access never runs on Linux/macOS (audited defect:
    # previously attempted on every non-psutil platform).
    if platform.system() != "Windows":
        return None, None
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
        return (
            (stat.ullTotalPhys - stat.ullAvailPhys) / (1024 * 1024),
            "windows-globalmemorystatus",
        )
    except (OSError, AttributeError, ImportError, ValueError):
        # ImportError/ValueError: ctypes.wintypes does not exist on
        # non-Windows builds; AttributeError: no windll. Fail soft to
        # (None, None) on every platform.
        return None, None


def _cpu_util_sample() -> tuple[float | None, str | None]:
    """System-wide CPU utilization percent as (value, source)."""
    try:
        import psutil

        return psutil.cpu_percent(interval=None), "psutil.cpu_percent"
    except ImportError:
        return None, None


class TelemetrySampler:
    """Sample hardware telemetry at a fixed interval in a daemon thread."""

    def __init__(self, interval_seconds: float = 0.5) -> None:
        self.interval = interval_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._samples: list[dict[str, Any]] = []
        self._sources: dict[str, str | None] = {}

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self.interval * 4 + 2)

    _SCOPE = {
        "ram_mb": "system",
        "cpu_util_percent": "system",
        "vram_mb": "device",
        "gpu_util_percent": "device",
        "temperature_c": "device",
        "power_watts": "device",
    }

    def summary(self) -> dict[str, Any]:
        """Aggregate collected samples into peak/average metrics.

        Keys are stable across versions; provenance (scope/source/device)
        lives in :meth:`provenance` so summaries stay merge-compatible
        with historical ``metrics`` blocks.
        """
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

    def provenance(self) -> dict[str, Any]:
        """Scope/source/device metadata for the collected telemetry.

        Returned separately from :meth:`summary` so result documents can
        carry a top-level ``telemetry`` block that states *what was
        measured* (system-wide vs device), *how* (psutil / Windows API /
        nvidia-smi), and *which device* was actually sampled — without
        changing the shape of ``metrics`` summaries.
        """
        with self._lock:
            samples = list(self._samples)
        device: dict[str, Any] | None = None
        for sample in samples:
            if sample.get("gpu_device_index") is not None:
                device = {
                    "gpu_device_index": sample.get("gpu_device_index"),
                    "gpu_device_name": sample.get("gpu_device_name"),
                }
                break
        block: dict[str, Any] = {
            "source": "aihwbench-telemetry",
            "interval_seconds": self.interval,
            "scope": dict(self._SCOPE),
            "sources": dict(self._sources),
            "samples": len(samples),
        }
        if device is not None:
            block["device"] = device
        npu_block = npu_snapshot_safe()
        if npu_block is not None:
            block["npu"] = npu_block
        return block

    def raw_trace(self) -> list[dict[str, Any]]:
        """Timestamped raw samples (epoch seconds), oldest first.

        Optional storage: attach to result artifacts that want the full
        time series instead of only the summary aggregates. Never
        required — summaries remain the canonical published metrics.
        """
        with self._lock:
            return [dict(sample) for sample in self._samples]

    def _loop(self) -> None:
        while not self._stop.is_set():
            started = time.time()
            ram_mb, ram_source = _system_ram_sample()
            cpu_util, cpu_source = _cpu_util_sample()
            sample: dict[str, Any] = {
                "timestamp": started,
                "ram_mb": ram_mb,
                "cpu_util_percent": cpu_util,
                "vram_mb": None,
                "gpu_util_percent": None,
                "temperature_c": None,
                "power_watts": None,
                "gpu_device_index": None,
                "gpu_device_name": None,
            }
            self._sources["ram_mb"] = ram_source
            self._sources["cpu_util_percent"] = cpu_source
            gpu = _nvidia_smi_sample()
            if gpu is not None:
                sample.update(gpu)
                for key in ("vram_mb", "gpu_util_percent", "temperature_c", "power_watts"):
                    self._sources[key] = "nvidia-smi"
            else:
                for key in ("vram_mb", "gpu_util_percent", "temperature_c", "power_watts"):
                    self._sources[key] = None
            with self._lock:
                self._samples.append(sample)
            time.sleep(self.interval)


def measure(fn: Callable[[], Any]) -> tuple[Any, float]:
    """Run fn and return (result, elapsed_ms)."""
    start = time.perf_counter()
    result = fn()
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    return result, elapsed_ms


def npu_snapshot_safe():
    """Best-effort NPU telemetry block (#18); None when no NPU is detected.

    Never raises. Uses the structured hook contract from
    :mod:`aihwbench.npu`: fields always exist, values stay ``None`` until
    a real driver counter is wired — nothing is fabricated.
    """
    try:
        from .npu import npu_telemetry

        block = npu_telemetry()
    except Exception:  # pragma: no cover - host-hardware dependent
        return None
    return block if block.get("npu_device") else None
