"""Thermal stability analysis (#23).

Consumes a sustained-load time series (throughput + temperature samples)
and reports peak vs steady-state throughput, the temperature curve,
time-to-throttle, and throughput degradation. All outputs are measured
from the supplied samples; an empty or too-short series yields None
fields rather than invented values.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "analyze_thermal_stability",
    "temperature_slope_c_per_min",
    "thermal_from_trace",
]

# A sample window is "steady state" once it is at least this long.
MIN_STEADY_SAMPLES = 5


def temperature_slope_c_per_min(
    timestamps_s: list[float], temperature_c: list[float]
) -> float | None:
    """Least-squares temperature slope in °C/minute.

    Measured from the supplied samples; returns ``None`` when fewer than
    two distinct timestamps are available (no trend can be measured).
    """
    n = len(timestamps_s)
    if n < 2 or n != len(temperature_c):
        return None
    if any(b < a for a, b in zip(timestamps_s, timestamps_s[1:], strict=False)):
        raise ValueError("timestamps must be non-decreasing")
    mean_t = sum(timestamps_s) / n
    mean_c = sum(temperature_c) / n
    var_t = sum((t - mean_t) ** 2 for t in timestamps_s)
    if var_t <= 0.0:
        return None
    cov = sum((t - mean_t) * (c - mean_c) for t, c in zip(timestamps_s, temperature_c, strict=True))
    slope_per_second = cov / var_t
    return round(slope_per_second * 60.0, 4)


def analyze_thermal_stability(
    timestamps_s: list[float],
    throughput_tps: list[float],
    temperature_c: list[float],
    throttle_temp_c: float = 85.0,
) -> dict[str, Any]:
    """Analyze a sustained-load run.

    ``timestamps_s`` are seconds since load start; all three lists must be
    equal length and time-ordered.
    """
    n = len(timestamps_s)
    if not (n == len(throughput_tps) == len(temperature_c)) or n < 2:
        return {
            "peak_throughput_tps": None,
            "steady_state_throughput_tps": None,
            "degradation_percent": None,
            "time_to_throttle_s": None,
            "max_temperature_c": None,
            "final_temperature_c": None,
            "temperature_slope_c_per_min": None,
            "temperature_curve": [],
            "reason": "insufficient samples for thermal analysis",
        }
    if any(b < a for a, b in zip(timestamps_s, timestamps_s[1:], strict=False)):
        raise ValueError("timestamps must be non-decreasing")

    peak = max(throughput_tps)
    # Steady state: mean of the final MIN_STEADY_SAMPLES window.
    window = throughput_tps[-MIN_STEADY_SAMPLES:]
    steady = sum(window) / len(window)
    degradation = ((peak - steady) / peak * 100.0) if peak > 0 else None

    throttle_at: float | None = None
    for t, temp in zip(timestamps_s, temperature_c, strict=True):
        if temp >= throttle_temp_c:
            throttle_at = t
            break

    return {
        "peak_throughput_tps": peak,
        "steady_state_throughput_tps": round(steady, 3),
        "degradation_percent": round(degradation, 2) if degradation is not None else None,
        "time_to_throttle_s": throttle_at,
        "throttle_threshold_c": throttle_temp_c,
        "max_temperature_c": max(temperature_c),
        "final_temperature_c": temperature_c[-1],
        "temperature_slope_c_per_min": temperature_slope_c_per_min(timestamps_s, temperature_c),
        "temperature_curve": [
            {"t_s": t, "temp_c": temp, "tps": tp}
            for t, temp, tp in zip(timestamps_s, temperature_c, throughput_tps, strict=True)
        ],
        "samples": n,
    }


def thermal_from_trace(
    series: list[dict[str, Any]],
    throttle_temp_c: float = 85.0,
) -> dict[str, Any]:
    """Thermal behaviour from a telemetry trace.

    :func:`analyze_thermal_stability` needs per-sample throughput and is the
    full sustained-load analysis. A telemetry trace records temperature and
    power over time but not throughput, so this reports exactly the subset the
    trace supports -- time to throttle, the temperature trend, peak and final
    temperature -- and returns the throughput fields as None with a reason
    rather than deriving them from data that was never collected.

    A laptop's 30-second burst number and its 30-minute sustained number can
    differ enormously, and this is the signal that distinguishes them.
    """
    points = [
        (float(s["timestamp"]), float(s["temperature_c"]))
        for s in series
        if s.get("timestamp") is not None and s.get("temperature_c") is not None
    ]
    if len(points) < 2:
        return {
            "samples": len(points),
            "max_temperature_c": points[0][1] if points else None,
            "final_temperature_c": points[0][1] if points else None,
            "temperature_slope_c_per_min": None,
            "time_to_throttle_s": None,
            "throttle_threshold_c": throttle_temp_c,
            "throttled": None,
            "reason": "fewer than two temperature samples; no trend can be measured",
        }

    points.sort(key=lambda p: p[0])
    start = points[0][0]
    elapsed = [t - start for t, _ in points]
    temps = [c for _, c in points]

    throttle_at: float | None = None
    for t, temp in zip(elapsed, temps, strict=True):
        if temp >= throttle_temp_c:
            throttle_at = round(t, 3)
            break

    return {
        "samples": len(points),
        "duration_s": round(elapsed[-1], 3),
        "max_temperature_c": max(temps),
        "final_temperature_c": temps[-1],
        "temperature_slope_c_per_min": temperature_slope_c_per_min(elapsed, temps),
        "time_to_throttle_s": throttle_at,
        "throttle_threshold_c": throttle_temp_c,
        "throttled": throttle_at is not None,
        "peak_throughput_tps": None,
        "steady_state_throughput_tps": None,
        "degradation_percent": None,
        "reason": (
            "temperature-only: a telemetry trace records no per-sample "
            "throughput, so peak-vs-steady-state degradation needs the "
            "sustained-load protocol (aihwbench suite --profile sustained)"
        ),
    }
