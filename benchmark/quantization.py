"""Quantization comparison (#19) and performance-quality frontier (#18).

``compare_quantizations`` groups result documents by model family and
tabulates speed, TTFT, memory, power, and optional quality per quant
variant — measured values only; variants missing a metric show None.

``performance_quality_frontier`` combines measured throughput with
evaluator mean scores to identify Pareto-optimal configurations without
collapsing anything into one opaque score.
"""

from __future__ import annotations

from typing import Any

from .sweep import pareto_frontier

__all__ = ["compare_quantizations", "performance_quality_frontier"]

_COMPARED_METRICS = (
    "generation_tokens_per_second",
    "ttft_ms",
    "peak_vram_mb",
    "average_power_watts",
)


def _model_family(name: str | None) -> str:
    """Best-effort family key from a model name ('llama-3.2-1b-q4' -> 'llama')."""
    if not name:
        return "unknown"
    return name.split("-")[0].split("/")[0].split(":")[0].lower()


def compare_quantizations(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Group results into model families and compare quant variants."""
    families: dict[str, list[dict[str, Any]]] = {}
    for r in results:
        model = r.get("model") or {}
        families.setdefault(_model_family(model.get("name")), []).append(r)

    out: dict[str, Any] = {"families": {}}
    for family, group in sorted(families.items()):
        rows = []
        for r in group:
            model = r.get("model") or {}
            metrics = r.get("metrics") or {}
            row: dict[str, Any] = {
                "run_id": r.get("run_id"),
                "model": model.get("name"),
                "quantization": model.get("quantization"),
                "format": model.get("format"),
            }
            for metric in _COMPARED_METRICS:
                row[metric] = metrics.get(metric)
            quality = r.get("quality")
            if isinstance(quality, dict):
                row["quality_mean_score"] = quality.get("mean_score")
            else:
                row["quality_mean_score"] = None
            rows.append(row)
        # Sort by throughput where measured; unmeasured sink to the end.
        rows.sort(key=lambda x: x["generation_tokens_per_second"] is not None, reverse=True)
        out["families"][family] = rows
    return out


def performance_quality_frontier(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Pareto frontier over (throughput max, quality max).

    Results lacking either a measured throughput or an evaluator score are
    excluded from the frontier and counted separately.
    """
    feasible: list[dict[str, Any]] = []
    excluded = 0
    for r in results:
        tps = (r.get("metrics") or {}).get("generation_tokens_per_second")
        quality = r.get("quality")
        score = quality.get("mean_score") if isinstance(quality, dict) else None
        if tps is None or score is None:
            excluded += 1
            continue
        feasible.append(
            {
                "run_id": r.get("run_id"),
                "metrics": {
                    "generation_tokens_per_second": tps,
                    "quality_mean_score": score,
                },
            }
        )
    front = pareto_frontier(
        feasible,
        {"generation_tokens_per_second": True, "quality_mean_score": True},
    )
    return {
        "frontier": front,
        "excluded_missing_data": excluded,
        "note": (
            "frontier requires both measured throughput and evaluator score; "
            "no single composite score is computed"
        ),
    }
