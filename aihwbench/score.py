"""Composite AIHWBench Score (optional, clearly-labeled heuristic).

Single-number scores are what buyers and the press ask for, but a single
number always hides detail. This module therefore:

  - normalizes each measured metric against a *published* reference point;
  - reports every component and weight alongside the total;
  - renormalizes weights when a metric was not measured (never invents one);
  - refuses to produce a score when throughput itself is missing.

The score is a convenience summary of measured metrics only. It is NOT a
scientific validity claim; always compare raw metrics for engineering work.
"""

from __future__ import annotations

from typing import Any

__all__ = ["REFERENCE_POINTS", "WEIGHTS", "compute_score"]

# Published normalization references (deliberately conservative mid-range
# laptop values). Changing these changes every score; treat as protocol.
REFERENCE_POINTS: dict[str, float] = {
    "generation_tokens_per_second": 50.0,  # tok/s considered "good" today
    "ttft_ms": 500.0,  # 0.5 s to first token feels interactive
    "performance_per_watt": 5.0,  # tok/s per watt on efficient laptops
}

WEIGHTS: dict[str, float] = {
    "throughput": 0.50,
    "responsiveness": 0.30,
    "efficiency": 0.20,
}

DISCLAIMER = (
    "Heuristic composite of measured metrics against published reference "
    "points; not a scientific-validity claim."
)


def _ratio(measured: float | None, reference: float) -> float | None:
    if measured is None or measured <= 0:
        return None
    return min(100.0, (measured / reference) * 100.0)


def _inverse_ratio(measured: float | None, reference: float) -> float | None:
    if measured is None or measured <= 0:
        return None
    return min(100.0, (reference / measured) * 100.0)


def compute_score(result: dict[str, Any]) -> dict[str, Any]:
    """Composite score with full breakdown for a validated result document."""
    metrics = result.get("metrics", {})

    components: dict[str, float | None] = {
        "throughput": _ratio(
            metrics.get("generation_tokens_per_second"),
            REFERENCE_POINTS["generation_tokens_per_second"],
        ),
        "responsiveness": _inverse_ratio(metrics.get("ttft_ms"), REFERENCE_POINTS["ttft_ms"]),
        "efficiency": _ratio(
            metrics.get("performance_per_watt"),
            REFERENCE_POINTS["performance_per_watt"],
        ),
    }

    missing = [name for name, value in components.items() if value is None]

    total: float | None = None
    if components["throughput"] is not None:
        active_weights = {
            name: WEIGHTS[name] for name, value in components.items() if value is not None
        }
        weight_sum = sum(active_weights.values())
        total = round(
            sum(components[name] * w for name, w in active_weights.items()) / weight_sum,
            1,
        )

    return {
        "run_id": result.get("run_id"),
        "score": total,
        "components": components,
        "weights_applied": {
            name: round(w / sum(active_weights.values()), 3) for name, w in active_weights.items()
        }
        if total is not None
        else {},
        "missing_metrics": missing,
        "reference_points": dict(REFERENCE_POINTS),
        "note": DISCLAIMER,
    }
