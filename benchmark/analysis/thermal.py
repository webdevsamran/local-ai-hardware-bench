"""Thermal stability analysis (#23).

Consumes a sustained-load time series (throughput + temperature samples)
and reports peak vs steady-state throughput, the temperature curve,
time-to-throttle, and throughput degradation. All outputs are measured
from the supplied samples; an empty or too-short series yields None
fields rather than invented values.
"""

from __future__ import annotations

from typing import Any

__all__ = ["analyze_thermal_stability"]

# A sample window is "steady state" once it is at least this long.
MIN_STEADY_SAMPLES = 5


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
        "temperature_curve": [
            {"t_s": t, "temp_c": temp, "tps": tp}
            for t, temp, tp in zip(timestamps_s, temperature_c, throughput_tps, strict=True)
        ],
        "samples": n,
    }
