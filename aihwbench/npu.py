"""NPU telemetry (#18) — and the counter that finally exists.

For a long time this module was a contract and nothing more: NPUs (Intel AI
Boost, AMD XDNA, Qualcomm Hexagon) exposed no portable, dependency-free
utilization counter, so the fields existed and stayed ``None`` rather than
being invented. That was the right answer and it is still the answer for most
of them.

Intel's Core Ultra NPU is the exception. Windows enumerates it in the
performance-counter tree as ``\\NPU Engine(*)\\Utilization Percentage``, the
same shape as ``\\GPU Engine(*)``, and Linux's ``intel_vpu`` driver exposes a
cumulative busy time under ``/sys/class/accel``. Both are readable without a
vendor SDK, so both are read.

**When it is read matters more than how.** A utilization figure taken after a
benchmark finishes describes an idle NPU, and would report a real accelerated
run as roughly 0% busy — a fabricated zero dressed as a measurement, which is
worse than the honest ``None`` this module shipped before. So the counter is
sampled by `TelemetrySampler` *during* the run alongside CPU and GPU, and what
lands in a result is the average and peak over the measured window.

**Cost is paid only where the counter exists.** Reading a Windows performance
counter means spawning PowerShell, which is expensive at a 0.5s cadence. The
sampler asks once whether this machine has an NPU engine at all and skips the
probe entirely when it does not — which is every machine without a Core Ultra,
including this project's own reference laptop.
"""

from __future__ import annotations

import platform
import subprocess
from pathlib import Path
from typing import Any

__all__ = [
    "NPU_FIELDS",
    "npu_telemetry",
    "npu_utilization_percent",
    "npu_counters_available",
]

NPU_FIELDS = ("npu_util_percent", "npu_power_watts", "npu_memory_used_mb")

#: Windows counter set for the Intel Core Ultra NPU, mirroring `\GPU Engine`.
_WINDOWS_COUNTER = r"\NPU Engine(*)\Utilization Percentage"

#: Where the Linux `intel_vpu` driver reports cumulative busy time.
_LINUX_ACCEL_GLOB = "/sys/class/accel/accel*/device"


def _windows_npu_utilization() -> float | None:
    """Total NPU engine utilization on Windows, or None if unreadable.

    Summed across engine instances rather than averaged, matching how the
    equivalent GPU counter is read: each instance is one engine, and a device
    with one busy engine out of four is not 25% busy from the caller's point of
    view. Capped at 100 because summed instances can overshoot slightly.
    """
    script = (
        f"(Get-Counter '{_WINDOWS_COUNTER}' -ErrorAction Stop)."
        "CounterSamples | Measure-Object -Property CookedValue -Sum | "
        "Select-Object -ExpandProperty Sum"
    )
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=10.0,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    text = (completed.stdout or "").strip()
    if not text:
        return None
    try:
        return min(float(text), 100.0)
    except ValueError:
        return None


def _linux_npu_busy_paths() -> list[Path]:
    """Sysfs files reporting cumulative NPU busy time, if the driver exposes them."""
    import glob

    found: list[Path] = []
    for device_dir in glob.glob(_LINUX_ACCEL_GLOB):
        for name in ("npu_busy_time_us", "busy_time_us"):
            candidate = Path(device_dir) / name
            if candidate.is_file():
                found.append(candidate)
    return found


def _linux_npu_utilization(interval_seconds: float = 0.1) -> float | None:
    """Busy percentage from the intel_vpu driver's cumulative counter.

    The kernel reports microseconds of busy time since boot, so a percentage
    needs two readings. The interval is deliberately short: this runs inside a
    sampling loop, and a longer window would smear the very transitions the
    trace exists to show.
    """
    import time

    paths = _linux_npu_busy_paths()
    if not paths:
        return None

    def total_busy_us() -> int | None:
        total = 0
        for path in paths:
            try:
                total += int(path.read_text().strip())
            except (OSError, ValueError):
                return None
        return total

    first = total_busy_us()
    if first is None:
        return None
    time.sleep(interval_seconds)
    second = total_busy_us()
    if second is None or second < first:
        return None
    busy_us = second - first
    window_us = interval_seconds * 1_000_000.0
    return min((busy_us / window_us) * 100.0, 100.0)


def npu_utilization_percent() -> float | None:
    """How busy the NPU is right now, or None where nothing reports it.

    None means unreadable, and callers must not record it as zero: "no counter
    on this platform" and "the accelerator did nothing" are different claims
    and only one of them is a measurement.
    """
    if platform.system() == "Windows":
        return _windows_npu_utilization()
    if platform.system() == "Linux":
        return _linux_npu_utilization()
    return None


def npu_counters_available() -> bool:
    """Whether this machine reports an NPU counter worth sampling.

    Asked once, before a run, so the sampling loop does not spawn PowerShell
    twice a second on the overwhelming majority of machines that have no NPU
    at all.
    """
    if platform.system() == "Linux":
        return bool(_linux_npu_busy_paths())
    if platform.system() == "Windows":
        return _windows_npu_utilization() is not None
    return False


def npu_telemetry(
    system: dict[str, Any] | None = None,
    measured: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """NPU telemetry block, measured where a counter exists.

    ``npu_device`` mirrors the detected NPU string (``system_info`` already
    sanitizes it). ``measured`` carries aggregates collected *during* the run
    by :class:`~aihwbench.telemetry.TelemetrySampler`; without it the metric
    fields stay ``None``, because a reading taken now would describe an idle
    device rather than the benchmark.

    ``npu_telemetry_source`` always states why a value is absent, so a
    consumer never mistakes "not measured" for "measured zero".
    """
    device = (system or {}).get("npu") or None
    values = {field: None for field in NPU_FIELDS}
    source = "no NPU detected" if not device else "driver counters not wired for this platform"

    if measured:
        for field in NPU_FIELDS:
            if measured.get(field) is not None:
                values[field] = measured[field]
        if values["npu_util_percent"] is not None:
            source = measured.get("source") or "sampled during the run"

    out: dict[str, Any] = {"npu_device": device, "npu_telemetry_source": source}
    out.update(values)
    # Peak alongside mean: an NPU that averaged 30% may have been saturated in
    # bursts, and the two answer different questions about headroom.
    if measured and measured.get("npu_util_percent_peak") is not None:
        out["npu_util_percent_peak"] = measured["npu_util_percent_peak"]
    return out
