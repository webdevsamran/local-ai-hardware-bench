"""The sweep projection must carry what its consumers ask for.

`run_sweep` copies a fixed list of metric names out of each result and
discards everything else. Three separate defects came from that list being
shorter than what reads from it, and each looked like a platform limitation
rather than a projection dropping a measured value:

- the cliff finder compared means with no intervals, and named an optimum that
  8 iterations later turned out to be the wrong setting;
- the tuner's `most_efficient` verdict was `None` for every sweep ever run,
  and its balanced frontier silently lost the efficiency axis;
- neither could tell a real difference from run-to-run noise.

The projection is worth keeping — a sweep of 40 points carrying entire result
documents is unwieldy — so this pins the list against the code that reads it
instead. A consumer asking for a metric the projection drops fails here rather
than returning a confident null in production.
"""

from __future__ import annotations

import ast
import pathlib

from aihwbench.sweep import DEFAULT_METRIC_KEYS

ROOT = pathlib.Path(__file__).resolve().parent.parent

#: Modules that read metrics off sweep-matrix rows.
_CONSUMERS = (
    "aihwbench/analysis/tune.py",
    "aihwbench/analysis/cliff.py",
    "aihwbench/analysis/context.py",
)


def _metric_names_read(path: pathlib.Path) -> set[str]:
    """Every known metric name that appears as a literal in the module.

    Matching against the canonical registry rather than against a syntactic
    shape is what makes this reliable. The first version looked for
    `metrics.get("x")` and `row["metrics"]["x"]`, and missed the defect it was
    written for: `tune.py` passes the name to a helper --
    `pick_best("performance_per_watt", True)` -- and subscripts with a
    variable, so no literal ever appears next to the word `metrics`.

    Filtering by the registry means a literal used any way at all is caught,
    and an unrelated string cannot be mistaken for a metric.
    """
    from aihwbench.metrics import METRIC_REGISTRY

    tree = ast.parse(path.read_text(encoding="utf-8"))
    known = set(METRIC_REGISTRY)
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value in known
    }


def test_consumers_are_actually_scanned():
    """A parser that found nothing would pass the test below trivially."""
    found = {name for path in _CONSUMERS for name in _metric_names_read(ROOT / path)}
    assert "generation_tokens_per_second" in found, f"parser found only: {sorted(found)}"


def test_projection_carries_every_metric_its_consumers_read():
    known = set(DEFAULT_METRIC_KEYS)
    missing: dict[str, set[str]] = {}
    for path in _CONSUMERS:
        gaps = _metric_names_read(ROOT / path) - known
        if gaps:
            missing[path] = gaps
    assert not missing, (
        "these modules read metrics the sweep projection drops, so they will "
        f"see null in production: {missing}. Add them to DEFAULT_METRIC_KEYS."
    )


def test_the_tuner_can_reach_its_own_verdicts():
    """`most_efficient` was None for every sweep ever run."""
    assert "performance_per_watt" in DEFAULT_METRIC_KEYS
    assert "peak_vram_mb" in DEFAULT_METRIC_KEYS
    assert "generation_tokens_per_second" in DEFAULT_METRIC_KEYS


def test_the_projection_carries_a_spread_not_just_a_mean():
    """Comparing configurations without one cannot distinguish a difference
    from a fluctuation, which is the whole job of a sweep."""
    assert "gen_tps_ci95" in DEFAULT_METRIC_KEYS
    assert "generation_tps_cv" in DEFAULT_METRIC_KEYS


def test_the_projection_actually_copies_the_metrics_it_declares():
    """The list is only a promise until something runs through it.

    Exercised with a synthetic backend because the two ends cannot meet on
    this machine: llama.cpp declares tunable axes but reports no prompt-eval
    duration, and Ollama reports one but declares no axes to sweep.
    """
    from aihwbench.sweep import SweepSpec, run_sweep

    def fake_run(point):
        return {
            "metrics": {
                "generation_tokens_per_second": 100.0,
                "prompt_tokens_per_second": 7516.56,
                "performance_per_watt": 3.4,
                "peak_vram_mb": 632.0,
                "gen_tps_ci95": [95.0, 105.0],
                "generation_tps_cv": 0.05,
                # Not projected, and must not be: a sweep of 40 points
                # carrying whole result documents is unusable.
                "some_unlisted_field": 1,
            }
        }

    matrix = run_sweep(
        SweepSpec(axes={"context_length": (512, 2048)}, base={"runtime": "fake"}),
        fake_run,
    )
    assert len(matrix) == 2
    metrics = matrix[0]["metrics"]
    assert metrics["prompt_tokens_per_second"] == 7516.56
    assert metrics["performance_per_watt"] == 3.4
    assert metrics["gen_tps_ci95"] == [95.0, 105.0]
    assert "some_unlisted_field" not in metrics
