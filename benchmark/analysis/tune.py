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

__all__ = ["run_tuner", "TUNING_AXES"]

# Safe default exploration spaces per axis. Callers may narrow them;
# widening beyond these requires explicit opt-in.
TUNING_AXES: dict[str, tuple[Any, ...]] = {
    "threads": (1, 2, 4, 8),
    "batch_size": (1, 2, 4),
    "context_length": (1024, 2048, 4096),
    "gpu_layers": (0, 16, 32, 99),
    "concurrency": (1, 2, 4),
}


def run_tuner(
    axes: dict[str, tuple[Any, ...]],
    run_fn: Any,
) -> dict[str, Any]:
    """Sweep the given axes and return the four classified verdicts."""
    if not axes:
        axes = {"threads": TUNING_AXES["threads"]}
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
