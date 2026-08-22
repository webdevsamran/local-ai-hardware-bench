"""Comparison of two benchmark result documents.

Comparisons are only meaningful when the model and workload match.
This module warns clearly about incomparable results so published
comparisons stay scientifically defensible.
"""

from __future__ import annotations

from typing import Any

NL = chr(10)

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
    warnings: list[str] = []
    ma, mb = a.get("model", {}), b.get("model", {})
    if ma.get("name") != mb.get("name"):
        warnings.append(
            f"models differ: {ma.get('name')!r} vs {mb.get('name')!r} - "
            "results are NOT directly comparable"
        )
    ra, rb = a.get("reproducibility", {}), b.get("reproducibility", {})
    for field in ("max_tokens", "temperature", "context_length"):
        va, vb = ra.get(field), rb.get(field)
        if va is not None and vb is not None and va != vb:
            warnings.append(f"workload differs: {field}={va} vs {vb}")
    sa, sb = a.get("system", {}), b.get("system", {})
    if sa.get("cpu") != sb.get("cpu") or sa.get("gpu") != sb.get("gpu"):
        warnings.append("hardware differs between results - treat as cross-platform reference only")
    return warnings


def compare_results(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """Compare metric-by-metric; returns a structured comparison."""
    ma, mb = a.get("metrics", {}), b.get("metrics", {})
    rows: list[dict[str, Any]] = []
    for key in _COMPARABLE_METRICS:
        va, vb = ma.get(key), mb.get(key)
        delta = None
        delta_pct = None
        if va is not None and vb is not None and va != 0:
            delta = round(vb - va, 3)
            delta_pct = round((vb - va) / abs(va) * 100.0, 1)
        rows.append({
            "metric": key,
            "a": va,
            "b": vb,
            "delta_b_minus_a": delta,
            "delta_percent": delta_pct,
        })
    return {
        "a_run_id": a.get("run_id"),
        "b_run_id": b.get("run_id"),
        "warnings": comparability_warnings(a, b),
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
    for warning in comparison["warnings"]:
        lines.append(f"> WARNING: {warning}")
    if comparison["warnings"]:
        lines.append("")
    lines.append("| Metric | A | B | Delta (B-A) | Delta % |")
    lines.append("| --- | --- | --- | --- | --- |")
    for row in comparison["metrics"]:
        lines.append(
            f"| {row['metric']} | {cell(row['a'])} | {cell(row['b'])} "
            f"| {cell(row['delta_b_minus_a'])} | {cell(row['delta_percent'])} |"
        )
    return NL.join(lines)