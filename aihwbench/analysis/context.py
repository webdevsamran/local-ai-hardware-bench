"""Context-depth scaling: how performance degrades as context grows.

A benchmark run at one context length is a single point on a curve, and it is
usually the flattering point. Prefill cost grows with input length, the KV
cache grows with it linearly, and both eventually collide with the memory the
machine has. Where a given machine falls off is the number people actually
need before committing to a workflow that uses long prompts.

This reads a sweep over ``context_length`` and reports three things the curve
shows and a single measurement cannot:

- **prefill scaling** — whether prompt processing degrades faster than
  linearly with input length, which is what makes a long-context workflow
  unusable rather than merely slower;
- **memory saturation** — the context at which measured VRAM stops growing,
  which usually means it started spilling rather than that it stopped needing
  more;
- **the last usable depth** — the deepest context still above a throughput
  floor the caller sets.

Everything is measured from the supplied points. Nothing is extrapolated: a
context depth that was not benchmarked has no entry, because the whole reason
this exists is that the curve is not predictable from one point.
"""

from __future__ import annotations

from typing import Any

__all__ = ["analyze_context_scaling", "CONTEXT_AXIS"]

#: Sweep axis holding the configured context length in tokens.
CONTEXT_AXIS = "context_length"

#: Growth beyond this multiple of linear is superlinear enough to matter.
#: Attention is quadratic in sequence length, so some superlinearity is
#: expected; this marks where it stops being a detail.
_SUPERLINEAR_FACTOR = 1.5

#: VRAM growth below this fraction between adjacent depths reads as saturation
#: rather than as a model that stopped needing memory.
_SATURATION_GROWTH = 0.02


def _metric(row: dict[str, Any], name: str) -> float | None:
    value = (row.get("metrics") or {}).get(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def analyze_context_scaling(
    matrix: list[dict[str, Any]],
    axis: str = CONTEXT_AXIS,
    min_acceptable_tps: float | None = None,
) -> dict[str, Any]:
    """Analyse a sweep across context depths.

    ``matrix`` is a sweep matrix: rows of ``{"params": {...}, "metrics": {...}}``.
    Rows missing the axis are excluded and counted; a row that ran but recorded
    no throughput still contributes its memory reading, because the two
    questions are independent.
    """
    points: list[dict[str, Any]] = []
    excluded = 0
    for row in matrix:
        depth = (row.get("params") or {}).get(axis)
        if not isinstance(depth, (int, float)) or isinstance(depth, bool):
            excluded += 1
            continue
        points.append(
            {
                "context_tokens": int(depth),
                "generation_tokens_per_second": _metric(row, "generation_tokens_per_second"),
                "prompt_tokens_per_second": _metric(row, "prompt_tokens_per_second"),
                "ttft_ms": _metric(row, "ttft_ms"),
                "peak_vram_mb": _metric(row, "peak_vram_mb"),
            }
        )

    if len(points) < 2:
        return {
            "axis": axis,
            "points": len(points),
            "excluded_missing_axis": excluded,
            "curve": points,
            "prefill_scaling": None,
            "memory_saturation_tokens": None,
            "last_usable_context_tokens": None,
            "reason": (
                f"need at least two measured depths on the {axis!r} axis; a "
                "scaling curve cannot be drawn through one point"
            ),
        }

    points.sort(key=lambda p: p["context_tokens"])

    # Prefill scaling: TTFT against context depth. Doubling the context should
    # at best double the prefill; markedly worse than that is the signal.
    prefill: dict[str, Any] | None = None
    ttft_points = [p for p in points if p["ttft_ms"] is not None and p["ttft_ms"] > 0]
    if len(ttft_points) >= 2:
        first, last = ttft_points[0], ttft_points[-1]
        depth_ratio = last["context_tokens"] / first["context_tokens"]
        ttft_ratio = last["ttft_ms"] / first["ttft_ms"]
        if depth_ratio > 1:
            superlinearity = ttft_ratio / depth_ratio
            prefill = {
                "from_tokens": first["context_tokens"],
                "to_tokens": last["context_tokens"],
                "depth_ratio": round(depth_ratio, 3),
                "ttft_ratio": round(ttft_ratio, 3),
                # 1.0 means TTFT grew exactly in step with context.
                "superlinearity": round(superlinearity, 3),
                "superlinear": superlinearity >= _SUPERLINEAR_FACTOR,
                "note": (
                    "attention is quadratic in sequence length, so some "
                    "superlinearity is expected; this flags where it stops "
                    "being a detail"
                ),
            }

    # Memory saturation: the depth from which VRAM stops climbing and stays
    # flat for the rest of the curve.
    #
    # The persistence requirement is the whole check. Testing a single
    # adjacent pair reported saturation at the second measured depth for any
    # model whose weights dominate its VRAM -- measured here as 614, 620, 632,
    # 658, 710 MB across 512 to 8192 tokens, where the 1% step from 512 to
    # 1024 was called saturation and the note offered spilling as the likely
    # cause, on a 16 GB card with 15 GB free. Memory that is still climbing at
    # the last point has not saturated, whatever any one pair did.
    saturation: int | None = None
    vram_points = [p for p in points if p["peak_vram_mb"]]
    for index in range(1, len(vram_points)):
        flat_from_here = all(
            (vram_points[i]["peak_vram_mb"] - vram_points[i - 1]["peak_vram_mb"])
            / vram_points[i - 1]["peak_vram_mb"]
            < _SATURATION_GROWTH
            for i in range(index, len(vram_points))
        )
        if flat_from_here:
            saturation = vram_points[index]["context_tokens"]
            break

    # Deepest context still above the caller's throughput floor.
    last_usable: int | None = None
    if min_acceptable_tps is not None:
        usable = [
            p["context_tokens"]
            for p in points
            if p["generation_tokens_per_second"] is not None
            and p["generation_tokens_per_second"] >= min_acceptable_tps
        ]
        last_usable = max(usable) if usable else None

    return {
        "axis": axis,
        "points": len(points),
        "excluded_missing_axis": excluded,
        "curve": points,
        "prefill_scaling": prefill,
        "memory_saturation_tokens": saturation,
        "memory_saturation_note": (
            # Two readings fit this evidence and the analyser cannot choose
            # between them from the curve alone, so it states both rather than
            # asserting the alarming one. Whether the card had headroom is
            # what separates them, and that is in the sweep's environment
            # block, not here.
            "VRAM stopped growing from this depth and stayed flat. On a card "
            "near its limit that means the run began spilling; on one with "
            "headroom it means the KV cache is small next to the weights. "
            "Compare peak VRAM against the card's capacity to tell which"
            if saturation is not None
            else (
                "VRAM was still growing at the deepest measured context, so "
                "nothing saturated in this range"
                if len(vram_points) > 1
                else None
            )
        ),
        "min_acceptable_tps": min_acceptable_tps,
        "last_usable_context_tokens": last_usable,
        "note": (
            "measured depths only; a context length that was not benchmarked "
            "has no entry, because the curve is not predictable from one point"
        ),
    }
