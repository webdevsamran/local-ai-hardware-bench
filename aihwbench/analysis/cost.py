"""Cost/performance and TCO (#26).

All monetary inputs are user-supplied (hardware cost, electricity price,
utilization). The repository never scrapes or hard-codes live prices.
Outputs: tokens/$, performance/$, and optional multi-year TCO with the
assumptions recorded inline.
"""

from __future__ import annotations

from typing import Any

__all__ = ["compute_cost_metrics"]


def compute_cost_metrics(
    hardware_cost_usd: float | None = None,
    electricity_usd_per_kwh: float | None = None,
    average_power_watts: float | None = None,
    generation_tokens_per_second: float | None = None,
    utilization_hours_per_day: float | None = None,
    years: int | None = None,
) -> dict[str, Any]:
    """Compute cost-efficiency metrics from user-supplied inputs.

    ``utilization_hours_per_day`` defaults to 24 only when computing TCO
    explicitly; it is always echoed so the assumption is visible.
    """
    out: dict[str, Any] = {
        "tokens_per_dollar": None,
        "energy_cost_per_1k_tokens_usd": None,
        "tco": None,
        "inputs": {
            "hardware_cost_usd": hardware_cost_usd,
            "electricity_usd_per_kwh": electricity_usd_per_kwh,
            "average_power_watts": average_power_watts,
            "generation_tokens_per_second": generation_tokens_per_second,
            "utilization_hours_per_day": utilization_hours_per_day,
            "years": years,
        },
    }
    if hardware_cost_usd and hardware_cost_usd > 0 and generation_tokens_per_second:
        # Tokens per dollar assumes one year of continuous operation at the
        # measured throughput; the assumption is stated, not hidden.
        tokens_first_year = generation_tokens_per_second * 3600.0 * 24.0 * 365.0
        out["tokens_per_dollar"] = round(tokens_first_year / hardware_cost_usd, 1)
        out["inputs"]["tokens_per_dollar_assumption"] = (
            "year-1 tokens at measured throughput / hardware cost"
        )
    if (
        electricity_usd_per_kwh
        and electricity_usd_per_kwh > 0
        and average_power_watts is not None
        and generation_tokens_per_second
        and generation_tokens_per_second > 0
    ):
        kwh_per_token = (average_power_watts / 1000.0) / generation_tokens_per_second
        out["energy_cost_per_1k_tokens_usd"] = round(
            kwh_per_token * 1000.0 * electricity_usd_per_kwh, 6
        )
    if (
        hardware_cost_usd
        and hardware_cost_usd > 0
        and electricity_usd_per_kwh
        and electricity_usd_per_kwh > 0
        and average_power_watts is not None
        and utilization_hours_per_day is not None
        and years
        and years > 0
    ):
        kwh_total = (average_power_watts / 1000.0) * utilization_hours_per_day * 365.0 * years
        energy_cost = kwh_total * electricity_usd_per_kwh
        out["tco"] = {
            "hardware_usd": hardware_cost_usd,
            "energy_usd": round(energy_cost, 2),
            "total_usd": round(hardware_cost_usd + energy_cost, 2),
            "years": years,
            "utilization_hours_per_day": utilization_hours_per_day,
        }
    return out
