"""Local ownership against cloud API spend.

Cloud pricing is caller-supplied and never bundled. Provider prices change
often, and a stale price table shipped inside a benchmark keeps producing
confident wrong answers long after anyone checks it -- the same reason the
competitor landscape is fetched rather than hardcoded.
"""

from __future__ import annotations

import re

import pytest

from aihwbench.analysis.cost import compare_local_vs_cloud


def test_cloud_cost_scales_with_volume_and_price():
    report = compare_local_vs_cloud(
        tokens_per_month=1_000_000,
        cloud_usd_per_million_tokens=2.0,
        hardware_cost_usd=1000,
        years=1,
    )
    assert report["cloud_monthly_usd"] == 2.0
    assert report["cloud_cost_usd"] == 24.0


def test_local_energy_uses_measured_power_and_throughput():
    """Producing the month's tokens takes a measurable amount of time."""
    report = compare_local_vs_cloud(
        tokens_per_month=3_600_000,
        cloud_usd_per_million_tokens=1.0,
        hardware_cost_usd=0,
        electricity_usd_per_kwh=0.50,
        average_power_watts=1000.0,
        generation_tokens_per_second=1000.0,
        years=1,
    )
    # 3.6M tokens at 1000 tok/s is 3600 s = 1 h; 1 kW for 1 h at $0.50 = $0.50.
    assert report["local_monthly_energy_usd"] == pytest.approx(0.5)


def test_break_even_is_hardware_cost_over_monthly_saving():
    report = compare_local_vs_cloud(
        tokens_per_month=10_000_000,
        cloud_usd_per_million_tokens=10.0,  # $100/month
        hardware_cost_usd=1200,
        electricity_usd_per_kwh=0.0,
        average_power_watts=0.0,
        generation_tokens_per_second=100.0,
        years=3,
    )
    # No energy cost, so $1200 of hardware against $100/month saved.
    assert report["break_even_months"] == 12.0
    assert report["cheaper"] == "local"


def test_hardware_that_never_pays_for_itself_says_so():
    """A huge break-even number reads as a figure; 'never' reads as an answer."""
    report = compare_local_vs_cloud(
        tokens_per_month=1000,  # trivial volume
        cloud_usd_per_million_tokens=0.01,
        hardware_cost_usd=2000,
        electricity_usd_per_kwh=0.40,
        average_power_watts=300.0,
        generation_tokens_per_second=40.0,
    )
    assert report["break_even_months"] is None
    assert "never pays for itself" in report["reason"]


def test_the_answer_can_be_that_cloud_wins():
    """An honest calculator must be able to conclude against local hardware."""
    report = compare_local_vs_cloud(
        tokens_per_month=20_000_000,
        cloud_usd_per_million_tokens=0.60,
        hardware_cost_usd=1800,
        electricity_usd_per_kwh=0.30,
        average_power_watts=180.0,
        generation_tokens_per_second=45.0,
        years=3,
    )
    assert report["cheaper"] == "cloud"
    assert report["savings_usd"] < 0


@pytest.mark.parametrize(
    ("tokens", "price", "expected"),
    [
        (None, 1.0, "monthly token volume is required"),
        (0, 1.0, "monthly token volume is required"),
        (1000, None, "cloud price per million tokens is required"),
    ],
)
def test_missing_inputs_are_reported_not_defaulted(tokens, price, expected):
    report = compare_local_vs_cloud(tokens, price)
    assert report["cloud_cost_usd"] is None
    assert expected in report["reason"]


def test_no_hardware_cost_means_no_ownership_comparison():
    report = compare_local_vs_cloud(1_000_000, 1.0, hardware_cost_usd=None)
    assert report["cloud_cost_usd"] is not None
    assert report["local_cost_usd"] is None
    assert "hardware cost is required" in report["reason"]


def test_no_price_table_is_bundled():
    """The module must not ship provider prices that can go stale.

    Checked by shape rather than by a list of provider names. The list version
    only caught the providers somebody thought to enumerate, so a table added
    for a provider not on it would have passed -- and the list needed
    maintaining forever to stay useful. A per-token or per-million-token price
    constant has a recognisable form whoever sells it, so that is what this
    looks for.
    """
    import ast
    from pathlib import Path

    from aihwbench.analysis import cost

    source = Path(cost.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)

    #: Names that would hold a bundled price rather than a caller-supplied one.
    price_like = re.compile(r"(price|pricing|rate|cost).*(table|per_million|per_token|usd)", re.I)

    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        names = [t.id for t in targets if isinstance(t, ast.Name)]
        if not any(price_like.search(n) for n in names):
            continue
        # A module-level constant holding numbers is a bundled table; a
        # parameter default of None is not.
        value = node.value
        if isinstance(value, (ast.Dict, ast.List, ast.Tuple)) or isinstance(
            getattr(value, "value", None), (int, float)
        ):
            offenders.append(names)

    assert not offenders, (
        f"cost.py appears to bundle a price table ({offenders}). Prices are "
        "supplied by the caller, because any rate committed here is wrong the "
        "day a provider changes it and nothing in the repository would notice."
    )
