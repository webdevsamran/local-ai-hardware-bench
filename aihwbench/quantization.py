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

__all__ = [
    "compare_quantizations",
    "performance_quality_frontier",
    "has_quality_signal",
    "QualitySignalMissing",
]


class QualitySignalMissing(RuntimeError):
    """Raised when a quantization comparison would carry no quality signal.

    Publishing tokens-per-second across quantization levels with nothing said
    about output quality actively misleads a reader into choosing a worse
    configuration: lower precision is faster *and* changes what the model says.
    A speed-only quantization table is the one output this project must not
    produce by accident.
    """


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
            quality = r.get("quality") if isinstance(r.get("quality"), dict) else {}
            row["quality_mean_score"] = quality.get("mean_score")
            # Measured on every generative run, unlike an evaluator score:
            # two quantizations that produce the same output hash said exactly
            # the same thing, and two that differ did not.
            row["output_hash"] = quality.get("output_hash")
            row["deterministic"] = quality.get("deterministic")
            rows.append(row)
        # Sort by throughput where measured; unmeasured sink to the end.
        rows.sort(key=lambda x: x["generation_tokens_per_second"] is not None, reverse=True)
        _annotate_output_agreement(rows)
        out["families"][family] = rows
    out["quality_signal"] = {
        "rows": sum(len(rows) for rows in out["families"].values()),
        "rows_with_signal": sum(
            1 for rows in out["families"].values() for row in rows if _row_has_signal(row)
        ),
    }
    return out


# Highest precision first: the reference a quantized variant is judged against.
_PRECISION_ORDER = (
    "fp32",
    "bf16",
    "fp16",
    "f16",
    "q8_0",
    "q8",
    "int8",
    "q6_k",
    "q5_k_m",
    "q5_k_s",
    "q5_0",
    "q4_k_m",
    "q4_k_s",
    "q4_0",
    "q3_k_m",
    "q3_k_s",
    "q2_k",
)


def _precision_rank(quantization: str | None) -> int:
    """Position in `_PRECISION_ORDER`; unknown labels sort last."""
    label = (quantization or "").lower()
    return _PRECISION_ORDER.index(label) if label in _PRECISION_ORDER else len(_PRECISION_ORDER)


def _row_has_signal(row: dict[str, Any]) -> bool:
    return row.get("quality_mean_score") is not None or row.get("output_hash") is not None


def _annotate_output_agreement(rows: list[dict[str, Any]]) -> None:
    """Mark whether each variant reproduced the highest-precision output.

    The reference is the highest-precision variant in the family that captured
    an output hash. ``same_output_as_reference`` is None when either side has
    no hash -- an unknown answer, never assumed agreement.
    """
    hashed = [r for r in rows if r.get("output_hash")]
    if not hashed:
        for row in rows:
            row["reference_quantization"] = None
            row["same_output_as_reference"] = None
        return
    reference = min(hashed, key=lambda r: _precision_rank(r.get("quantization")))
    for row in rows:
        row["reference_quantization"] = reference.get("quantization")
        if not row.get("output_hash"):
            row["same_output_as_reference"] = None
        else:
            row["same_output_as_reference"] = row["output_hash"] == reference["output_hash"]


def has_quality_signal(comparison: dict[str, Any]) -> bool:
    """True when at least one compared row carries any quality signal."""
    signal = comparison.get("quality_signal") or {}
    return bool(signal.get("rows_with_signal"))


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
