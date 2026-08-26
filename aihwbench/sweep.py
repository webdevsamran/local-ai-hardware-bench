"""Parameter sweep engine (#5).

Explores combinations of batch size, concurrency, threads, GPU layers,
device, model/runtime options and workload parameters, producing a
structured result matrix.

The engine is runtime-agnostic: callers inject a ``run_fn(config) -> dict``
that executes one point (the CLI wires the real backend runner; tests use
fakes). Every matrix row records the exact parameter values that produced
it plus the measured metrics of the run — nothing is interpolated.
"""

from __future__ import annotations

import itertools
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

__all__ = ["SweepSpec", "run_sweep", "matrix_to_csv_rows", "best_by", "pareto_frontier"]

RunFn = Callable[[dict[str, Any]], dict[str, Any]]

DEFAULT_METRIC_KEYS = (
    "generation_tokens_per_second",
    "ttft_ms",
    "total_latency_ms",
    "peak_vram_mb",
    "average_power_watts",
)


@dataclass(frozen=True)
class SweepSpec:
    """Cartesian-product sweep over named axes."""

    axes: dict[str, tuple[Any, ...]]
    base: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if not self.axes:
            raise ValueError("sweep requires at least one axis")
        for name, values in self.axes.items():
            if not name or any(c.isspace() for c in name):
                raise ValueError(f"axis name must be non-empty without whitespace: {name!r}")
            if not values:
                raise ValueError(f"axis {name!r} must have at least one value")

    def combinations(self) -> list[dict[str, Any]]:
        names = sorted(self.axes)
        combos = []
        for values in itertools.product(*(self.axes[n] for n in names)):
            point = dict(self.base or {})
            point.update(dict(zip(names, values, strict=True)))
            combos.append(point)
        return combos


def run_sweep(
    spec: SweepSpec,
    run_fn: RunFn,
    metric_keys: tuple[str, ...] = DEFAULT_METRIC_KEYS,
) -> list[dict[str, Any]]:
    """Execute every combination and return the structured matrix.

    A failing combination is recorded with ``error`` set rather than
    aborting the whole sweep — partial matrices are honest matrices.
    """
    rows: list[dict[str, Any]] = []
    for point in spec.combinations():
        row: dict[str, Any] = {"params": point}
        try:
            result = run_fn(point)
            metrics = result.get("metrics", {}) if isinstance(result, dict) else {}
            row["metrics"] = {k: metrics.get(k) for k in metric_keys}
            row["run_id"] = result.get("run_id") if isinstance(result, dict) else None
            row["error"] = None
        except Exception as exc:  # noqa: BLE001 - record failure per-point
            row["metrics"] = {k: None for k in metric_keys}
            row["run_id"] = None
            row["error"] = str(exc)
        rows.append(row)
    return rows


def matrix_to_csv_rows(
    matrix: list[dict[str, Any]],
    metric_keys: tuple[str, ...] = DEFAULT_METRIC_KEYS,
) -> list[dict[str, str | float | int | None]]:
    """Flatten the nested matrix into flat CSV-ready rows."""
    flat: list[dict[str, str | float | int | None]] = []
    for row in matrix:
        entry: dict[str, str | float | int | None] = {}
        for key, value in sorted(row["params"].items()):
            entry[f"param_{key}"] = value if isinstance(value, (str, int, float)) else str(value)
        for key in metric_keys:
            entry[key] = row["metrics"].get(key)
        entry["run_id"] = row.get("run_id")
        entry["error"] = row.get("error")
        flat.append(entry)
    return flat


def best_by(
    matrix: list[dict[str, Any]],
    metric: str,
    maximize: bool = True,
) -> dict[str, Any] | None:
    """Return the matrix row with the best measured value of ``metric``."""
    candidates = [r for r in matrix if r.get("metrics", {}).get(metric) is not None]
    if not candidates:
        return None
    if maximize:
        return max(candidates, key=lambda r: r["metrics"][metric])
    return min(candidates, key=lambda r: r["metrics"][metric])


def pareto_frontier(
    matrix: list[dict[str, Any]],
    objectives: Mapping[str, bool],
) -> list[dict[str, Any]]:
    """Pareto-optimal rows under mixed maximize/minimize objectives.

    ``objectives`` maps metric name -> True (maximize) / False (minimize).
    Rows missing an objective value are excluded from frontier analysis.
    """
    feasible = [
        r for r in matrix if all(r.get("metrics", {}).get(m) is not None for m in objectives)
    ]
    front: list[dict[str, Any]] = []
    for candidate in feasible:
        dominated = False
        for other in feasible:
            if other is candidate:
                continue
            better_or_equal = True
            strictly_better = False
            for metric, maximize in objectives.items():
                a = candidate["metrics"][metric]
                b = other["metrics"][metric]
                if maximize:
                    if b < a:
                        better_or_equal = False
                        break
                    if b > a:
                        strictly_better = True
                else:
                    if b > a:
                        better_or_equal = False
                        break
                    if b < a:
                        strictly_better = True
            if better_or_equal and strictly_better:
                dominated = True
                break
        if not dominated:
            front.append(candidate)
    return front
