"""Battery drain during sustained local inference.

A laptop's throughput number is only half the story: the other half is how
long the machine can sustain it away from mains power. Nobody publishes that,
and it is one of the few figures a laptop owner can act on directly.

The drain rate is measured from the telemetry trace, not modelled. Samples
taken while plugged in are excluded rather than averaged in -- a machine on
mains power is charging or holding, and folding that into a discharge rate
would understate it or invert its sign.
"""

from __future__ import annotations

from typing import Any

__all__ = ["battery_profile"]

#: Minimum discharge needed before a rate is worth quoting. Below this the
#: figure is dominated by the battery gauge's own resolution, which steps in
#: whole percent on most hardware.
MIN_DISCHARGE_PERCENT = 1.0


def battery_profile(series: list[dict[str, Any]]) -> dict[str, Any]:
    """Discharge rate and projected runtime from a telemetry trace.

    Returns ``rate_percent_per_hour`` and a projection of how long the battery
    would last at that rate. Both are None unless the machine actually
    discharged during the run: a short benchmark on a full battery cannot
    measure a drain rate, and inventing one would be worse than saying so.
    """
    points = [
        (float(s["timestamp"]), float(s["battery_percent"]), bool(s.get("on_ac_power")))
        for s in series
        if s.get("timestamp") is not None and s.get("battery_percent") is not None
    ]
    if not points:
        return {
            "measured": False,
            "samples": 0,
            "rate_percent_per_hour": None,
            "projected_runtime_hours": None,
            "reason": "no battery telemetry in this run (desktop, or no battery sensor)",
        }

    points.sort(key=lambda p: p[0])
    on_battery = [(t, pct) for t, pct, ac in points if not ac]
    if len(on_battery) < 2:
        return {
            "measured": False,
            "samples": len(points),
            "samples_on_battery": len(on_battery),
            "rate_percent_per_hour": None,
            "projected_runtime_hours": None,
            "start_percent": points[0][1],
            "end_percent": points[-1][1],
            "reason": (
                "the machine was on mains power for this run; unplug to measure a discharge rate"
            ),
        }

    start_t, start_pct = on_battery[0]
    end_t, end_pct = on_battery[-1]
    elapsed_hours = (end_t - start_t) / 3600.0
    discharged = start_pct - end_pct

    if elapsed_hours <= 0 or discharged < MIN_DISCHARGE_PERCENT:
        return {
            "measured": False,
            "samples": len(points),
            "samples_on_battery": len(on_battery),
            "rate_percent_per_hour": None,
            "projected_runtime_hours": None,
            "start_percent": start_pct,
            "end_percent": end_pct,
            "discharged_percent": round(discharged, 2),
            "reason": (
                f"discharged {discharged:.2f}% over {elapsed_hours * 60:.1f} min, "
                f"below the {MIN_DISCHARGE_PERCENT}% needed for a rate the "
                "battery gauge can actually resolve"
            ),
        }

    rate = discharged / elapsed_hours
    return {
        "measured": True,
        "samples": len(points),
        "samples_on_battery": len(on_battery),
        "start_percent": start_pct,
        "end_percent": end_pct,
        "discharged_percent": round(discharged, 2),
        "elapsed_hours": round(elapsed_hours, 4),
        "rate_percent_per_hour": round(rate, 2),
        # From full, at this rate. Real runtime is worse near empty and
        # depends on the battery's health, so this is a ceiling.
        "projected_runtime_hours": round(100.0 / rate, 2) if rate > 0 else None,
        "note": (
            "measured while unplugged, under this workload only; projected "
            "runtime extrapolates a constant rate from a full charge and is "
            "an upper bound"
        ),
    }
