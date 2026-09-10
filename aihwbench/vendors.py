"""Vendor telemetry collectors beyond NVIDIA.

Throughput without power and thermal context is a half-truth, and until now
only NVIDIA GPUs supplied that context: every AMD, Intel and Apple result
carried nulls for power and temperature. That is not a small gap — energy and
thermals on consumer hardware is one of the few things no competing local-AI
benchmark measures at all.

**Parsing is separated from probing on purpose.** Each vendor has a pure
``parse_*`` function that turns captured tool output into a sample, and a
``*_sample`` function that runs the tool and delegates. The parsers are fully
tested against captured fixtures on any machine; the probes can only be
exercised on the hardware in question.

That split is also an honesty boundary. The parsers are verified. The output
formats they expect come from each vendor's documentation and have **not** been
confirmed against real hardware by this project — every backend without a
tested machine is marked ``HARDWARE_REQUIRED`` for exactly this reason, and
telemetry deserves the same treatment. A parser that meets output it does not
recognise returns ``None`` rather than a guess, so an unverified format
produces missing data, never wrong data.
"""

from __future__ import annotations

import json
import re
import subprocess
from typing import Any

__all__ = [
    "parse_rocm_smi",
    "parse_powermetrics",
    "parse_rapl_energy",
    "rocm_sample",
    "powermetrics_sample",
    "rapl_power_sample",
    "read_rapl_counter",
    "battery_sample",
    "VENDOR_STATUS",
]

#: What has actually been confirmed on hardware, per vendor. Kept beside the
#: code so a reader does not have to infer support from the presence of a
#: function.
VENDOR_STATUS: dict[str, str] = {
    "nvidia": "tested — nvidia-smi on the reference machine",
    "amd": "parser tested against captured output; rocm-smi not run on real hardware",
    "intel": "parser tested against captured output; RAPL not read on real hardware",
    "apple": "parser tested against captured output; powermetrics not run on real hardware",
    "battery": "tested — psutil.sensors_battery on the reference laptop",
}


def _num(value: Any) -> float | None:
    """Best-effort numeric conversion; None rather than a guess."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if not isinstance(value, str):
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", value)
    return float(match.group(0)) if match else None


# --------------------------------------------------------------------- AMD


def parse_rocm_smi(payload: str) -> dict[str, Any] | None:
    """Parse ``rocm-smi --json`` output into a telemetry sample.

    ROCm labels its keys with the sensor and unit in the key name itself
    ("Temperature (Sensor edge) (C)"), and the exact wording varies between
    driver versions. Keys are therefore matched on substrings rather than
    exact strings, which survives a rename that an exact match would not.

    Returns None when the payload is not ROCm JSON or contains no card.
    """
    try:
        data = json.loads(payload)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None

    cards = {k: v for k, v in data.items() if k.lower().startswith("card") and isinstance(v, dict)}
    if not cards:
        return None
    index = sorted(cards)[0]
    card = cards[index]

    def find(*needles: str) -> float | None:
        for key, value in card.items():
            lowered = key.lower()
            if all(needle in lowered for needle in needles):
                return _num(value)
        return None

    return {
        # Matched on the unit, not the wording: ROCm reports both
        # "GPU memory use (MB)" and "GPU Memory Allocated (VRAM%)", and
        # reading the percentage as megabytes would be badly wrong rather
        # than merely missing.
        "vram_mb": find("memory", "(mb)"),
        "vram_percent": find("memory", "vram%"),
        "gpu_util_percent": find("gpu use"),
        # "edge" is the die sensor; junction and memory sensors also exist and
        # read higher. Picking one and saying which beats averaging them.
        "temperature_c": find("temperature", "edge") or find("temperature"),
        "power_watts": find("average", "power") or find("power"),
        "gpu_device_index": index,
        "gpu_device_name": str(card.get("Card series") or card.get("Card SKU") or index),
        "telemetry_vendor": "amd",
    }


def rocm_sample() -> dict[str, Any] | None:
    """One AMD GPU sample via ``rocm-smi``. None when unavailable."""
    try:
        proc = subprocess.run(
            ["rocm-smi", "--showuse", "--showmemuse", "--showtemp", "--showpower", "--json"],
            capture_output=True,
            text=True,
            timeout=5.0,
            encoding="utf-8",
            errors="replace",
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return parse_rocm_smi(proc.stdout)


# ------------------------------------------------------------------- Apple


_POWERMETRICS_FIELDS = (
    ("cpu_power_mw", re.compile(r"^CPU Power:\s*([\d.]+)\s*mW", re.MULTILINE)),
    ("gpu_power_mw", re.compile(r"^GPU Power:\s*([\d.]+)\s*mW", re.MULTILINE)),
    (
        "package_power_mw",
        re.compile(r"^Combined Power \(CPU \+ GPU[^)]*\):\s*([\d.]+)\s*mW", re.MULTILINE),
    ),
)


def parse_powermetrics(payload: str) -> dict[str, Any] | None:
    """Parse ``powermetrics`` output into a telemetry sample.

    Apple Silicon reports power in milliwatts and splits it by domain. The
    package figure is preferred where present because it is what an energy
    figure should be measured against; falling back to CPU+GPU is stated in
    the sample rather than silently substituted.
    """
    if not isinstance(payload, str) or not payload.strip():
        return None
    found: dict[str, float] = {}
    for name, pattern in _POWERMETRICS_FIELDS:
        match = pattern.search(payload)
        if match:
            found[name] = float(match.group(1))
    if not found:
        return None

    package_mw = found.get("package_power_mw")
    basis = "package"
    if package_mw is None:
        parts = [found.get("cpu_power_mw"), found.get("gpu_power_mw")]
        measured = [p for p in parts if p is not None]
        package_mw = sum(measured) if measured else None
        basis = "cpu+gpu" if measured else "none"

    return {
        "power_watts": round(package_mw / 1000.0, 3) if package_mw is not None else None,
        "cpu_power_watts": (
            round(found["cpu_power_mw"] / 1000.0, 3) if "cpu_power_mw" in found else None
        ),
        "gpu_power_watts": (
            round(found["gpu_power_mw"] / 1000.0, 3) if "gpu_power_mw" in found else None
        ),
        "power_basis": basis,
        "telemetry_vendor": "apple",
    }


def powermetrics_sample() -> dict[str, Any] | None:
    """One Apple Silicon power sample. None when unavailable.

    ``powermetrics`` requires elevated privileges; a permission failure is
    reported as unavailable rather than raised, because a benchmark should not
    die over optional telemetry.
    """
    try:
        proc = subprocess.run(
            ["powermetrics", "--samplers", "cpu_power,gpu_power", "-n", "1", "-i", "200"],
            capture_output=True,
            text=True,
            timeout=10.0,
            encoding="utf-8",
            errors="replace",
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return parse_powermetrics(proc.stdout)


# ------------------------------------------------------------------- Intel


def parse_rapl_energy(
    energy_uj_start: float | None,
    energy_uj_end: float | None,
    elapsed_seconds: float,
    max_energy_uj: float | None = None,
) -> dict[str, Any] | None:
    """Average power from two Intel RAPL energy-counter readings.

    RAPL exposes cumulative energy in microjoules, not power, so a reading is
    only meaningful as a difference over a known interval. The counter wraps
    at a device-specific maximum; when that maximum is known a wrap is
    corrected, and when it is not, a negative delta is reported as
    unmeasurable rather than as a nonsensical negative power.
    """
    if energy_uj_start is None or energy_uj_end is None or elapsed_seconds <= 0:
        return None
    delta_uj = energy_uj_end - energy_uj_start
    wrapped = delta_uj < 0
    if wrapped:
        if max_energy_uj is None or max_energy_uj <= 0:
            return None
        delta_uj += max_energy_uj
    joules = delta_uj / 1_000_000.0
    return {
        "power_watts": round(joules / elapsed_seconds, 3),
        "energy_joules": round(joules, 6),
        "interval_seconds": elapsed_seconds,
        "counter_wrapped": wrapped,
        "telemetry_vendor": "intel",
        "scope": "package (RAPL); CPU domain only, excludes a discrete GPU",
    }


def read_rapl_counter(path: str) -> float | None:
    """One raw RAPL sysfs counter, or None where it is unreadable.

    Public because the telemetry sampler reads the counter directly: it ticks
    on its own schedule and cannot use ``rapl_power_sample``, which sleeps to
    get its second reading.
    """
    try:
        with open(path, encoding="utf-8") as handle:
            return float(handle.read().strip())
    except (OSError, ValueError):
        return None


def rapl_power_sample(
    interval_seconds: float = 0.5,
    domain: str = "/sys/class/powercap/intel-rapl:0",
) -> dict[str, Any] | None:
    """Average CPU-package power over ``interval_seconds`` via Intel RAPL.

    Linux only: the counter lives in sysfs. Returns None everywhere else,
    which is honest — this measures nothing on Windows.
    """
    import time

    start = read_rapl_counter(f"{domain}/energy_uj")
    if start is None:
        return None
    time.sleep(interval_seconds)
    end = read_rapl_counter(f"{domain}/energy_uj")
    return parse_rapl_energy(
        start,
        end,
        interval_seconds,
        max_energy_uj=read_rapl_counter(f"{domain}/max_energy_range_uj"),
    )


# ----------------------------------------------------------------- battery


def battery_sample() -> dict[str, Any] | None:
    """Battery charge and whether the machine is on mains power.

    Sampled over a sustained run this gives the figure laptop owners actually
    want and nobody publishes: how long local inference lasts unplugged. A
    single reading is only the input; the drain rate comes from the trace.

    Returns None on a machine with no battery, which is most desktops.
    """
    try:
        import psutil
    except ImportError:
        return None
    try:
        battery = psutil.sensors_battery()
    except (AttributeError, OSError):  # pragma: no cover - platform dependent
        return None
    if battery is None:
        return None
    seconds_left = getattr(battery, "secsleft", None)
    # psutil reports sentinels for "charging" and "unknown"; both mean there is
    # no meaningful estimate, and reporting them as a duration would be wrong.
    if seconds_left is not None and seconds_left < 0:
        seconds_left = None
    return {
        "battery_percent": round(float(battery.percent), 2),
        "on_ac_power": bool(battery.power_plugged),
        "battery_seconds_left": seconds_left,
    }
