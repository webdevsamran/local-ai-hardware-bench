"""Comparison of two benchmark result documents.

Comparisons are only meaningful when the model and workload match. This
module uses an explicit comparability classifier (see comparability.py)
and refuses to emit metric deltas when results are NOT_COMPARABLE.
"""

from __future__ import annotations

from typing import Any

from .comparability import (
    CONDITIONALLY_COMPARABLE,
    NOT_COMPARABLE,
    STRICTLY_COMPARABLE,
    compare_classification,
)

NL = chr(10)

COMPARABILITY_VALUES = (STRICTLY_COMPARABLE, CONDITIONALLY_COMPARABLE, NOT_COMPARABLE)

_COMPARABLE_METRICS = [
    "load_time_ms",
    "ttft_ms",
    "prompt_tokens_per_second",
    "generation_tokens_per_second",
    "total_latency_ms",
    "p50_latency_ms",
    "p95_latency_ms",
    "average_power_watts",
    "performance_per_watt",
]


def comparability_warnings(a: dict[str, Any], b: dict[str, Any]) -> list[str]:
    """Return warnings when two results are not materially comparable."""
    reasons: list[str] = compare_classification(a, b)["reasons"]
    return reasons


def compare_results(a: dict[str, Any], b: dict[str, Any], force: bool = False) -> dict[str, Any]:
    """Compare metric-by-metric; returns a structured comparison.

    When the classification is NOT_COMPARABLE and ``force`` is False, no
    delta rows are emitted (the comparison is returned as-is with the
    machine-readable classification and reasons).
    """
    classification = compare_classification(a, b)
    ma, mb = a.get("metrics", {}), b.get("metrics", {})
    rows: list[dict[str, Any]] = []
    if classification["classification"] != NOT_COMPARABLE or force:
        for key in _COMPARABLE_METRICS:
            va, vb = ma.get(key), mb.get(key)
            delta = None
            delta_pct = None
            if va is not None and vb is not None and va != 0:
                delta = round(vb - va, 3)
                delta_pct = round((vb - va) / abs(va) * 100.0, 1)
            rows.append(
                {
                    "metric": key,
                    "a": va,
                    "b": vb,
                    "delta_b_minus_a": delta,
                    "delta_percent": delta_pct,
                }
            )
    return {
        "a_run_id": a.get("run_id"),
        "b_run_id": b.get("run_id"),
        "classification": classification["classification"],
        "reasons": classification["reasons"],
        "machine_reasons": classification["machine_reasons"],
        "warnings": classification["reasons"],
        "metrics": rows,
    }


def render_comparison(comparison: dict[str, Any]) -> str:
    """Render a comparison as markdown."""

    def cell(value: Any) -> str:
        if value is None:
            return "-"
        if isinstance(value, float):
            return f"{value:,.2f}"
        return str(value)

    lines: list[str] = []
    lines.append(f"# Comparison: {comparison['a_run_id']} -> {comparison['b_run_id']}")
    lines.append("")
    lines.append(f"**Classification:** {comparison['classification']}")
    lines.append("")
    for warning in comparison["warnings"]:
        lines.append(f"> WARNING: {warning}")
    if comparison["warnings"]:
        lines.append("")
    if not comparison["metrics"]:
        lines.append("No metrics compared: results are NOT_COMPARABLE. Use `--force` to override.")
        lines.append("")
        return NL.join(lines)
    lines.append("| Metric | A | B | Delta (B-A) | Delta % |")
    lines.append("| --- | --- | --- | --- | --- |")
    for row in comparison["metrics"]:
        lines.append(
            f"| {row['metric']} | {cell(row['a'])} | {cell(row['b'])} "
            f"| {cell(row['delta_b_minus_a'])} | {cell(row['delta_percent'])} |"
        )
    return NL.join(lines)
