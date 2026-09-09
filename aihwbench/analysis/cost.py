"""Cost/performance and TCO (#26).

All monetary inputs are user-supplied (hardware cost, electricity price,
utilization). The repository never scrapes or hard-codes live prices.
Outputs: tokens/$, performance/$, and optional multi-year TCO with the
assumptions recorded inline.
"""

from __future__ import annotations

from typing import Any

__all__ = ["compute_cost_metrics", "compare_local_vs_cloud"]


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


def compare_local_vs_cloud(
    tokens_per_month: float | None,
    cloud_usd_per_million_tokens: float | None,
    hardware_cost_usd: float | None = None,
    electricity_usd_per_kwh: float | None = None,
    average_power_watts: float | None = None,
    generation_tokens_per_second: float | None = None,
    years: int = 3,
) -> dict[str, Any]:
    """Compare owning hardware against paying a cloud API, over ``years``.

    ``cloud_usd_per_million_tokens`` is supplied by the caller and never
    bundled. Provider prices change often, and a stale price table shipped
    inside a benchmark would quietly produce wrong answers long after anyone
    noticed -- the same reason the competitor table is fetched rather than
    hardcoded. The caller reads today's price from the provider.

    The local side uses *measured* throughput and power where available, so
    the electricity figure reflects the machine actually benchmarked rather
    than a nameplate rating. Anything not supplied yields None: the break-even
    point is only as real as its inputs.
    """
    out: dict[str, Any] = {
        "years": years,
        "cloud_cost_usd": None,
        "local_cost_usd": None,
        "local_energy_usd": None,
        "savings_usd": None,
        "break_even_months": None,
        "cheaper": None,
        "inputs": {
            "tokens_per_month": tokens_per_month,
            "cloud_usd_per_million_tokens": cloud_usd_per_million_tokens,
            "hardware_cost_usd": hardware_cost_usd,
            "electricity_usd_per_kwh": electricity_usd_per_kwh,
            "average_power_watts": average_power_watts,
            "generation_tokens_per_second": generation_tokens_per_second,
        },
        "note": (
            "cloud price is caller-supplied and never bundled; local energy "
            "uses measured power and throughput where available"
        ),
    }
    if not tokens_per_month or tokens_per_month <= 0:
        out["reason"] = "monthly token volume is required"
        return out
    if cloud_usd_per_million_tokens is None or cloud_usd_per_million_tokens < 0:
        out["reason"] = "a cloud price per million tokens is required"
        return out

    months = years * 12
    cloud_monthly = (tokens_per_month / 1_000_000.0) * cloud_usd_per_million_tokens
    out["cloud_cost_usd"] = round(cloud_monthly * months, 2)
    out["cloud_monthly_usd"] = round(cloud_monthly, 2)

    # Local energy: how long the hardware must run to produce that many tokens.
    energy_monthly: float | None = None
    if (
        electricity_usd_per_kwh
        and average_power_watts is not None
        and generation_tokens_per_second
        and generation_tokens_per_second > 0
    ):
        seconds = tokens_per_month / generation_tokens_per_second
        kwh = (average_power_watts / 1000.0) * (seconds / 3600.0)
        energy_monthly = kwh * electricity_usd_per_kwh
        out["local_energy_usd"] = round(energy_monthly * months, 2)
        out["local_monthly_energy_usd"] = round(energy_monthly, 2)

    if hardware_cost_usd is None:
        out["reason"] = "hardware cost is required to compare against ownership"
        return out

    local_total = hardware_cost_usd + (energy_monthly or 0.0) * months
    out["local_cost_usd"] = round(local_total, 2)
    out["savings_usd"] = round(out["cloud_cost_usd"] - local_total, 2)
    out["cheaper"] = "local" if local_total < out["cloud_cost_usd"] else "cloud"

    # Break-even: months until cumulative cloud spend covers the hardware plus
    # the energy spent alongside it. If local monthly cost is not lower, it
    # never breaks even, and saying so beats reporting a huge number.
    monthly_delta = cloud_monthly - (energy_monthly or 0.0)
    if monthly_delta > 0:
        out["break_even_months"] = round(hardware_cost_usd / monthly_delta, 1)
    else:
        out["break_even_months"] = None
        out["reason"] = (
            "local running cost is not below the cloud cost at this volume, "
            "so buying hardware never pays for itself here"
        )
    return out
