"""Self-test and environment noise detection (#49).

``run_self_test`` performs precondition checks that are measurable on the
current machine without fabricating results:

- timer resolution (measured via perf_counter granularity)
- telemetry tool availability (nvidia-smi, powermetrics, etc.)
- background CPU load (psutil when installed; skipped otherwise)
- battery vs AC power state (psutil; skipped otherwise)
- power profile (Windows: powercfg /getactivescheme)
- thermal pressure (psutil sensors when available)
- runtime/model availability (backend registry detection)

Every check returns a status of pass/warn/skip/fail with measured detail.
Skips are honest: an unmeasurable check is reported as skipped, never
guessed.
"""

from __future__ import annotations

import platform
import shutil
import subprocess
import time
from typing import Any

__all__ = ["run_self_test"]


def _check_timer_resolution() -> dict[str, Any]:
    samples = []
    for _ in range(5):
        t0 = time.perf_counter()
        t1 = time.perf_counter()
        while t1 == t0:
            t1 = time.perf_counter()
        samples.append(t1 - t0)
    resolution_s = min(samples)
    status = "pass" if resolution_s < 1e-4 else "warn"
    return {
        "check": "timer_resolution",
        "status": status,
        "detail": f"perf_counter granularity ~{resolution_s * 1e6:.2f} us",
    }


def _check_telemetry_tools() -> dict[str, Any]:
    tools = {
        "nvidia-smi": "GPU utilization/power/temperature",
        "powermetrics": "macOS CPU/GPU power (requires sudo)",
        "rapl": "Linux RAPL energy counters",
    }
    found = [name for name in tools if shutil.which(name)]
    if found:
        return {"check": "telemetry", "status": "pass", "detail": f"available: {', '.join(found)}"}
    return {
        "check": "telemetry",
        "status": "skip",
        "detail": "no telemetry tools found; power/thermal metrics will be null",
    }


def _check_background_load() -> dict[str, Any]:
    try:
        import psutil
    except ImportError:
        return {
            "check": "background_load",
            "status": "skip",
            "detail": "psutil not installed; install it for load checks",
        }
    cpu = psutil.cpu_percent(interval=0.5)
    if cpu > 20.0:
        return {
            "check": "background_load",
            "status": "warn",
            "detail": f"CPU at {cpu:.0f}% before benchmarking — close other apps",
        }
    return {"check": "background_load", "status": "pass", "detail": f"CPU idle ({cpu:.0f}%)"}


def _check_power_source() -> dict[str, Any]:
    try:
        import psutil
    except ImportError:
        return {"check": "power_source", "status": "skip", "detail": "psutil not installed"}
    try:
        battery = psutil.sensors_battery()
    except (AttributeError, NotImplementedError):
        return {
            "check": "power_source",
            "status": "skip",
            "detail": "battery information unavailable on this system",
        }
    if battery is None:
        return {
            "check": "power_source",
            "status": "skip",
            "detail": "no battery detected (desktop or always-on AC)",
        }
    if battery.power_plugged:
        return {"check": "power_source", "status": "pass", "detail": "on AC power"}
    return {
        "check": "power_source",
        "status": "warn",
        "detail": "on battery — results may be throttled by OS power saving",
    }


def _check_power_profile() -> dict[str, Any]:
    if platform.system() != "Windows":
        return {
            "check": "power_profile",
            "status": "skip",
            "detail": "power profile check implemented for Windows",
        }
    try:
        proc = subprocess.run(
            ["powercfg", "/getactivescheme"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"check": "power_profile", "status": "skip", "detail": "powercfg unavailable"}
    output = (proc.stdout or "").strip()
    if not output:
        return {"check": "power_profile", "status": "skip", "detail": "no active scheme reported"}
    lowered = output.lower()
    if "power saver" in lowered:
        return {
            "check": "power_profile",
            "status": "warn",
            "detail": f"{output} — expect reduced performance",
        }
    return {"check": "power_profile", "status": "pass", "detail": output}


def _check_thermal_state() -> dict[str, Any]:
    try:
        import psutil
    except ImportError:
        return {"check": "thermal_state", "status": "skip", "detail": "psutil not installed"}
    get_temp = getattr(psutil, "sensors_temperatures", None)
    if get_temp is None:
        return {
            "check": "thermal_state",
            "status": "skip",
            "detail": "temperature sensors unsupported on this platform",
        }
    try:
        temps = get_temp()
    except (AttributeError, NotImplementedError):
        return {
            "check": "thermal_state",
            "status": "skip",
            "detail": "temperature sensors unavailable",
        }
    readings = [t.current for entries in temps.values() for t in entries if t.current]
    if not readings:
        return {
            "check": "thermal_state",
            "status": "skip",
            "detail": "no temperature sensor readings available",
        }
    hottest = max(readings)
    if hottest >= 85.0:
        return {
            "check": "thermal_state",
            "status": "warn",
            "detail": f"hottest sensor {hottest:.0f} C — let hardware cool first",
        }
    return {"check": "thermal_state", "status": "pass", "detail": f"hottest sensor {hottest:.0f} C"}


def _check_runtimes() -> dict[str, Any]:
    from .backends import detect_all

    ready = [i["name"] for i in detect_all() if i.get("status") == "ready"]
    if ready:
        return {"check": "runtimes", "status": "pass", "detail": f"ready: {', '.join(ready)}"}
    return {
        "check": "runtimes",
        "status": "fail",
        "detail": "no runtimes detected; install ollama or llama.cpp",
    }


_CHECKS = (
    _check_timer_resolution,
    _check_telemetry_tools,
    _check_background_load,
    _check_power_source,
    _check_power_profile,
    _check_thermal_state,
    _check_runtimes,
)


def run_self_test() -> dict[str, Any]:
    """Run all precondition checks; returns structured report."""
    results = [fn() for fn in _CHECKS]
    blocking = [r for r in results if r["status"] == "fail"]
    warnings = [r for r in results if r["status"] == "warn"]
    overall = "fail" if blocking else ("warn" if warnings else "pass")
    return {
        "overall": overall,
        "platform": platform.platform(),
        "checks": results,
        "summary": {
            "pass": sum(1 for r in results if r["status"] == "pass"),
            "warn": len(warnings),
            "skip": sum(1 for r in results if r["status"] == "skip"),
            "fail": len(blocking),
        },
    }
