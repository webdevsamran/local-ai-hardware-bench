"""Performance-per-watt must carry its unit.

`performance_per_watt` is throughput/watt, but "throughput" is tokens/s for
generative runtimes and inferences/s for graph ones. The value alone is not
self-describing, and for a while the leaderboard printed both in one column
and the per-run reports labelled every row "tok/s/W" -- including runs that
produced zero tokens. These tests pin the unit to the data.
"""

from __future__ import annotations

import json
from pathlib import Path

from aihwbench.metrics import (
    performance_per_watt,
    performance_per_watt_basis,
    performance_per_watt_unit,
)
from aihwbench.report import render_report

_GENERATIVE = {
    "generation_tokens_per_second": 360.87,
    "average_power_watts": 26.76,
    "performance_per_watt": 13.485,
}
_GRAPH = {
    "generation_tokens_per_second": None,
    "throughput_inferences_per_second": 299.92,
    "average_power_watts": 22.27,
    "performance_per_watt": 13.468,
}


def test_basis_follows_the_throughput_actually_measured() -> None:
    assert performance_per_watt_basis(_GENERATIVE) == "tokens"
    assert performance_per_watt_basis(_GRAPH) == "inferences"


def test_units_are_distinct() -> None:
    assert performance_per_watt_unit(_GENERATIVE) == "tok/s/W"
    assert performance_per_watt_unit(_GRAPH) == "inf/s/W"
    assert performance_per_watt_unit(_GENERATIVE) != performance_per_watt_unit(_GRAPH)


def test_unmeasured_perf_per_watt_has_no_basis() -> None:
    assert performance_per_watt_basis({"performance_per_watt": None}) is None
    assert performance_per_watt_basis({}) is None


def test_a_zero_token_run_is_never_labelled_tokens_per_watt() -> None:
    """The specific regression: an ONNX run reported as tok/s/W."""
    result = {
        "run_id": "graph-run",
        "runtime": {"name": "onnxruntime"},
        "model": {"name": "mobilenetv2-12.onnx"},
        "metrics": _GRAPH,
        "system": {},
        "reproducibility": {},
    }
    body = render_report(result)
    assert "inf/s/W" in body
    assert "tok/s/W" not in body


def test_published_results_agree_with_their_reports() -> None:
    """Every committed result's unit matches the report published beside it."""
    published = Path("results/published")
    reports = Path("docs/reports")
    if not published.is_dir():
        return
    checked = 0
    for result_file in sorted(published.glob("*.json")):
        report = reports / f"{result_file.stem}.md"
        if not report.is_file():
            continue
        metrics = json.loads(result_file.read_text(encoding="utf-8")).get("metrics", {})
        if metrics.get("performance_per_watt") is None:
            continue
        unit = performance_per_watt_unit(metrics)
        assert unit in report.read_text(encoding="utf-8"), (
            f"{report.name} does not state the correct Perf/W unit ({unit})"
        )
        checked += 1
    assert checked >= 1, "expected at least one published result to check"


def test_division_is_unit_agnostic() -> None:
    """The helper divides; it does not assume tokens."""
    assert performance_per_watt(299.92, 22.27) == performance_per_watt(299.92, 22.27)
    assert performance_per_watt(None, 22.27) is None
    assert performance_per_watt(299.92, None) is None
