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


#: A component at exactly this value hit the ceiling and stopped
#: distinguishing anything above it.
CEILING = 100.0


def _ratio(measured: float | None, reference: float) -> float | None:
    if measured is None or measured <= 0:
        return None
    return min(CEILING, (measured / reference) * 100.0)


def _inverse_ratio(measured: float | None, reference: float) -> float | None:
    if measured is None or measured <= 0:
        return None
    return min(CEILING, (reference / measured) * 100.0)


def _raw_ratio(measured: float | None, reference: float, *, inverse: bool = False) -> float | None:
    """The ratio before clamping, so a saturated component can say by how much."""
    if measured is None or measured <= 0:
        return None
    value = (reference / measured) if inverse else (measured / reference)
    return round(value * 100.0, 1)


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

    # What each component would have scored without the ceiling.
    #
    # Every component is clamped at 100, so anything at or above its reference
    # point scores exactly 100 — and two results at 2x and 10x the reference
    # are indistinguishable there. Measured on the reference machine, a run
    # scored 100.0 on both throughput and efficiency, leaving the composite
    # driven almost entirely by its remaining component. A number that has
    # stopped discriminating should say so rather than looking like a
    # measurement, which is the whole objection this project raises to
    # single-number scores.
    uncapped: dict[str, float | None] = {
        "throughput": _raw_ratio(
            metrics.get("generation_tokens_per_second"),
            REFERENCE_POINTS["generation_tokens_per_second"],
        ),
        "responsiveness": _raw_ratio(
            metrics.get("ttft_ms"), REFERENCE_POINTS["ttft_ms"], inverse=True
        ),
        "efficiency": _raw_ratio(
            metrics.get("performance_per_watt"),
            REFERENCE_POINTS["performance_per_watt"],
        ),
    }
    clamped = sorted(
        name for name, value in components.items() if value is not None and value >= CEILING
    )

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
        # Components that hit the ceiling, and what they would have been
        # without it. A reader comparing two results can see immediately
        # whether the score is still telling them anything.
        "components_at_ceiling": clamped,
        "uncapped_components": uncapped,
        "reference_points": dict(REFERENCE_POINTS),
        "note": (
            f"{DISCLAIMER} {len(clamped)} of {len(components)} components hit "
            "the 100-point ceiling, so the score does not distinguish this "
            "result from anything faster on them; see uncapped_components."
            if clamped
            else DISCLAIMER
        ),
    }
