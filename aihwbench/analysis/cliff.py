"""Offload-cliff analysis.

The single largest performance discontinuity in local inference is the moment
a model stops fitting in VRAM. Throughput does not degrade smoothly as layers
move to the CPU: it falls off a cliff, and where that cliff sits depends on the
machine — PCIe generation and width, memory bandwidth, how much VRAM the rest
of the desktop is using.

That makes it precisely the question a crowdsourced benchmark can answer and a
vendor benchmark cannot, because the answer is different on every machine. It
is also the question buyers actually ask, phrased as "will a 13B model be
usable on my card".

This module reads a sweep over the offload axis and reports where throughput
collapsed. It measures the drop between adjacent measured points; it does not
model, extrapolate, or predict an unmeasured configuration.
"""

from __future__ import annotations

from typing import Any

__all__ = ["find_offload_cliff", "OFFLOAD_AXIS", "CLIFF_DROP_THRESHOLD"]

#: Sweep axis holding the number of layers placed on the GPU.
OFFLOAD_AXIS = "gpu_layers"

#: A drop of at least this fraction between adjacent points is a cliff rather
#: than ordinary scaling. 25% is well outside run-to-run variance for a
#: warmed-up benchmark, and far below the 3-5x collapses seen in practice.
CLIFF_DROP_THRESHOLD = 0.25


def _throughput(row: dict[str, Any]) -> float | None:
    value = (row.get("metrics") or {}).get("generation_tokens_per_second")
    return float(value) if isinstance(value, (int, float)) else None


def find_offload_cliff(
    matrix: list[dict[str, Any]],
    axis: str = OFFLOAD_AXIS,
    threshold: float = CLIFF_DROP_THRESHOLD,
) -> dict[str, Any]:
    """Locate the throughput cliff across an offload sweep.

    ``matrix`` is the sweep matrix produced by :mod:`aihwbench.sweep`: rows of
    ``{"params": {...}, "metrics": {...}}``. Rows without a measured throughput
    or without the axis are excluded and counted, never treated as zero.

    Returns the largest relative drop between adjacent points, the layer count
    at which it happened, and the best fully-measured configuration. When
    fewer than two points are usable there is no cliff to report, and the
    result says so rather than inventing a knee.
    """
    points: list[tuple[float, float]] = []
    excluded = 0
    for row in matrix:
        params = row.get("params") or {}
        value = _throughput(row)
        layers = params.get(axis)
        if value is None or not isinstance(layers, (int, float)):
            excluded += 1
            continue
        points.append((float(layers), value))

    if len(points) < 2:
        return {
            "axis": axis,
            "points": len(points),
            "excluded_missing_data": excluded,
            "cliff_detected": None,
            "reason": (
                f"need at least two measured points on the {axis!r} axis; "
                "a cliff is a drop between adjacent configurations"
            ),
        }

    # Ascending layer count: more layers on the GPU should mean more speed, so
    # a fall as layers increase is itself worth surfacing.
    points.sort(key=lambda p: p[0])

    worst_drop = 0.0
    cliff_between: tuple[float, float] | None = None
    drops: list[dict[str, Any]] = []
    for (low_layers, low_tps), (high_layers, high_tps) in zip(points, points[1:], strict=False):
        # Reading downward: moving from the higher offload setting to the lower
        # one is what a user experiences when a model stops fitting.
        if high_tps <= 0:
            continue
        drop = (high_tps - low_tps) / high_tps
        drops.append(
            {
                "from_layers": high_layers,
                "to_layers": low_layers,
                "from_tps": high_tps,
                "to_tps": low_tps,
                "drop_fraction": round(drop, 4),
                "slowdown_factor": round(high_tps / low_tps, 3) if low_tps > 0 else None,
            }
        )
        if drop > worst_drop:
            worst_drop = drop
            cliff_between = (low_layers, high_layers)

    best_layers, best_tps = max(points, key=lambda p: p[1])
    return {
        "axis": axis,
        "points": len(points),
        "excluded_missing_data": excluded,
        "cliff_detected": worst_drop >= threshold,
        "threshold": threshold,
        "largest_drop_fraction": round(worst_drop, 4),
        "cliff_between_layers": list(cliff_between) if cliff_between else None,
        "best_layers": best_layers,
        "best_tokens_per_second": best_tps,
        "curve": [{"layers": layers, "tokens_per_second": tps} for layers, tps in points],
        "drops": drops,
        "note": (
            "measured points only; the cliff is the largest throughput drop "
            "between adjacent configurations, not a fitted or predicted knee"
        ),
    }
