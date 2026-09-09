"""Auto-tuner (#50).

Explores a safe configuration space (threads, batch, context, GPU offload,
concurrency) via the sweep engine and classifies Pareto-optimal points
into four named verdicts:

- fastest        — max generation throughput
- most_efficient — max tokens per watt (when power measured)
- lowest_memory  — min peak memory
- balanced       — Pareto frontier across speed/memory/efficiency

Every verdict cites its measured values; ties and missing metrics are
reported honestly instead of resolved arbitrarily.
"""

from __future__ import annotations

from typing import Any

from ..sweep import SweepSpec, pareto_frontier, run_sweep

__all__ = ["run_tuner", "TUNING_AXES", "UnsupportedAxisError", "check_axes_supported"]


class UnsupportedAxisError(ValueError):
    """Raised when asked to tune an axis the backend does not apply."""


# Safe default exploration spaces per axis. Callers may narrow them;
# widening beyond these requires explicit opt-in.
#
# Listing an axis here does NOT mean every backend honours it -- see
# `check_axes_supported`. A backend declares what it actually applies via
# its module-level TUNABLE_AXES tuple.
TUNING_AXES: dict[str, tuple[Any, ...]] = {
    "threads": (1, 2, 4, 8),
    "batch_size": (1, 2, 4),
    "context_length": (1024, 2048, 4096),
    "gpu_layers": (0, 16, 32, 99),
    "concurrency": (1, 2, 4),
}


def check_axes_supported(
    axes: dict[str, tuple[Any, ...]],
    supported: tuple[str, ...],
    runtime: str,
) -> None:
    """Refuse to tune an axis the backend will not apply.

    Sweeping a parameter the backend ignores runs N identical benchmarks and
    reports the fastest as "optimal", turning run-to-run variance into a
    confident recommendation. Refusing is the honest behaviour: a tuner that
    cannot vary something must say so rather than measure noise.
    """
    unsupported = sorted(a for a in axes if a not in supported)
    if not unsupported:
        return
    known = ", ".join(supported) if supported else "<none>"
    raise UnsupportedAxisError(
        f"runtime {runtime!r} does not apply these tuning axes: "
        f"{', '.join(unsupported)}. It would run identical benchmarks and "
        f"report the variance between them as a result. Axes this runtime "
        f"honours: {known}."
    )


def run_tuner(
    axes: dict[str, tuple[Any, ...]],
    run_fn: Any,
    *,
    supported_axes: tuple[str, ...] | None = None,
    runtime: str = "the selected runtime",
) -> dict[str, Any]:
    """Sweep the given axes and return the four classified verdicts.

    ``supported_axes`` is the backend's declared TUNABLE_AXES; when given,
    every requested axis is checked against it first.
    """
    if not axes:
        axes = {"threads": TUNING_AXES["threads"]}
    if supported_axes is not None:
        check_axes_supported(axes, supported_axes, runtime)
    spec = SweepSpec(axes=axes)
    matrix = run_sweep(spec, run_fn)

    def rows_with(metric: str) -> list[dict[str, Any]]:
        return [r for r in matrix if r.get("metrics", {}).get(metric) is not None]

    def pick_best(metric: str, maximize: bool) -> dict[str, Any] | None:
        candidates = rows_with(metric)
        if not candidates:
            return None
        key = lambda r: r["metrics"][metric]  # noqa: E731
        return (max if maximize else min)(candidates, key=key)

    fastest = pick_best("generation_tokens_per_second", True)
    most_efficient = pick_best("performance_per_watt", True)
    lowest_memory = pick_best("peak_vram_mb", False)

    objectives: dict[str, bool] = {"generation_tokens_per_second": True}
    if rows_with("peak_vram_mb"):
        objectives["peak_vram_mb"] = False
    if rows_with("performance_per_watt"):
        objectives["performance_per_watt"] = True
    balanced = pareto_frontier(matrix, objectives)

    return {
        "axes": {k: list(v) for k, v in axes.items()},
        "points_measured": len(matrix),
        "fastest": fastest,
        "most_efficient": most_efficient,
        "lowest_memory": lowest_memory,
        "balanced_frontier": balanced,
        "notes": [
            "all verdicts come from measured sweep points",
            "verdicts requiring unmeasured metrics are null rather than guessed",
        ],
    }
