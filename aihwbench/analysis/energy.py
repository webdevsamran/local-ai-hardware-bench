"""Energy metrics (#24, #25).

Computes joules/request, joules/token, and joules/1k tokens from measured
average power and throughput, plus gross vs incremental power when an
idle baseline was measured. Every output records its telemetry source and
measurement tier; missing inputs yield None, never estimates.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "compute_energy_metrics",
    "carbon_estimate",
    "MIN_ROBUST_INCREMENTAL_SHARE",
    "JOULES_PER_KWH",
]

#: Below this share of gross power, the incremental figure is mostly the
#: choice of baseline rather than the workload.
#:
#: Measured case: the same workload on the same machine yielded 0.0777 J/token
#: against a 14.9 W baseline and 0.0009 J/token against a 31.4 W one, because
#: the second run began with a model still resident and the card at raised
#: clocks. Both power readings were correct. What is not correct is presenting
#: the second J/token as a comparable measure of the same thing.
#:
#: When almost all the draw is baseline, small baseline differences swing the
#: result by orders of magnitude, so the number is reported *and* flagged --
#: withholding it would hide a real measurement, while publishing it bare
#: invites exactly the false comparison this project exists to prevent.
MIN_ROBUST_INCREMENTAL_SHARE = 0.10

#: Joules in a kilowatt-hour. Named because the conversion appears in three
#: places and a wrong constant here would be invisible: every figure derived
#: from it would still be internally consistent.
JOULES_PER_KWH = 3_600_000.0


def compute_energy_metrics(
    average_power_watts: float | None,
    idle_power_watts: float | None,
    generation_tokens_per_second: float | None,
    requests_per_second: float | None,
    telemetry_source: str | None = None,
    idle_power_spread_watts: float | None = None,
) -> dict[str, Any]:
    """Derive energy-per-unit metrics from measured power.

    ``telemetry_source`` (e.g. "nvidia-smi", "rapl", "external-meter") is
    echoed into the result so consumers know the measurement tier.
    """
    # Below-noise-floor is not zero.
    #
    # This used to clamp with max(0.0, gross - idle), which turned "the
    # workload's draw was not distinguishable from idle" into the confident
    # claim "this workload costs 0.0 J/token". Measured case: a 0.5B model on
    # an RTX 3080 Ti held the GPU at ~6% utilization, and the card's idle draw
    # drifted by more than the workload added -- gross 28.26 W against a
    # 29.62 W baseline. Both readings were sound; their difference was not
    # resolvable. Reporting None says that; reporting 0.0 asserts a free lunch.
    incremental_watts: float | None = None
    unresolved: str | None = None
    if average_power_watts is not None and idle_power_watts is not None:
        delta = average_power_watts - idle_power_watts
        if delta > 0:
            incremental_watts = delta
        else:
            unresolved = (
                f"average power under load ({average_power_watts} W) did not exceed "
                f"the idle baseline ({idle_power_watts} W), so the workload's own "
                "draw is below the resolution of this power sensor. Per-token "
                "energy is not reported: the measurement cannot distinguish a "
                "small cost from none at all"
            )

    def per_rate(watts: float | None, rate: float | None) -> float | None:
        if watts is None or rate is None or rate <= 0:
            return None
        return watts / rate

    j_per_token = per_rate(incremental_watts, generation_tokens_per_second)
    j_per_request = per_rate(incremental_watts, requests_per_second)

    # How much of the measured draw the benchmark is actually responsible for.
    share: float | None = None
    if (
        incremental_watts is not None
        and average_power_watts is not None
        and average_power_watts > 0
    ):
        share = round(incremental_watts / average_power_watts, 4)

    # A difference smaller than the spread of the thing subtracted is not a
    # measurement of the difference. Measured on the reference machine: idle
    # oscillated between 14 W and 21 W at 0% utilization, so a workload adding
    # 3 W produces an "incremental" figure the baseline could have accounted
    # for on its own.
    within_baseline_noise = (
        incremental_watts is not None
        and idle_power_spread_watts is not None
        and idle_power_spread_watts > 0
        and incremental_watts <= idle_power_spread_watts
    )

    robust: bool | None = None
    caveat: str | None = unresolved
    if within_baseline_noise:
        robust = False
        caveat = (
            f"the workload added {incremental_watts:.2f} W, within the "
            f"{idle_power_spread_watts:.2f} W the idle baseline varied by on "
            "its own. The difference is inside the noise of what was "
            "subtracted, so per-token energy here is not a measurement of the "
            "workload"
        )
    elif share is not None:
        robust = share >= MIN_ROBUST_INCREMENTAL_SHARE
        if not robust:
            caveat = (
                f"only {share:.1%} of measured power is attributable to the "
                "workload; the rest is the machine's idle draw. At this ratio "
                "the per-token energy figure is dominated by the baseline and "
                "should not be compared against a run whose baseline was "
                "measured in a different machine state"
            )

    return {
        # Gross power includes the idle baseline; incremental isolates the
        # benchmark's own consumption.
        "gross_average_power_watts": average_power_watts,
        "idle_baseline_power_watts": idle_power_watts,
        "incremental_power_watts": incremental_watts,
        "energy_joules_per_token": j_per_token,
        "energy_joules_per_request": j_per_request,
        "energy_joules_per_1k_tokens": (
            round(j_per_token * 1000.0, 4) if j_per_token is not None else None
        ),
        # The same measurement in the units people actually plan with. A
        # joule-per-token figure is correct and unusable for "how many tokens
        # can I generate for a kilowatt-hour", which is the form the question
        # takes when someone is comparing against a cloud bill or a battery.
        "tokens_per_kwh": (round(JOULES_PER_KWH / j_per_token) if j_per_token else None),
        "watt_hours_per_1k_tokens": (
            round(j_per_token * 1000.0 / 3600.0, 4) if j_per_token is not None else None
        ),
        "incremental_share_of_gross": share,
        # How much the idle baseline moved while being measured. Published
        # because it bounds how precise the incremental figure can be.
        "idle_power_spread_watts": idle_power_spread_watts,
        # False does not mean the measurement is wrong -- it means the figure
        # is mostly baseline and will not survive comparison across runs.
        "incremental_is_robust": robust,
        "caveat": caveat,
        "telemetry_source": telemetry_source,
        "measured_inputs": {
            "average_power_watts": average_power_watts is not None,
            "idle_power_watts": idle_power_watts is not None,
            "generation_tokens_per_second": generation_tokens_per_second is not None,
            "requests_per_second": requests_per_second is not None,
        },
    }


def carbon_estimate(
    energy: dict[str, Any] | None,
    grid_intensity_g_co2_per_kwh: float | None = None,
) -> dict[str, Any]:
    """Grams of CO2 per 1000 tokens, when the caller states their grid.

    Carbon is energy multiplied by a number this project cannot measure. Grid
    intensity varies by country, by season, and by hour: the same run in France
    and in Poland differs by roughly a factor of ten. A published figure using
    a global average would be a confident number that is wrong nearly
    everywhere, and wrong in a direction nobody could see.

    So the intensity is required rather than defaulted, the same way
    `analysis.cost` requires an electricity price instead of assuming one. With
    no intensity this returns the energy in kWh and says what is missing --
    which is still useful, because kWh is the input every published grid figure
    takes.
    """
    energy = energy or {}
    j_per_token = energy.get("energy_joules_per_token")
    if not isinstance(j_per_token, int | float) or j_per_token <= 0:
        return {
            "grams_co2_per_1k_tokens": None,
            "kwh_per_1k_tokens": None,
            "grid_intensity_g_co2_per_kwh": grid_intensity_g_co2_per_kwh,
            "unresolved": "no energy-per-token measurement to convert",
        }

    kwh_per_1k = (float(j_per_token) * 1000.0) / JOULES_PER_KWH

    if not isinstance(grid_intensity_g_co2_per_kwh, int | float) or (
        grid_intensity_g_co2_per_kwh <= 0
    ):
        return {
            "grams_co2_per_1k_tokens": None,
            "kwh_per_1k_tokens": round(kwh_per_1k, 9),
            "grid_intensity_g_co2_per_kwh": None,
            "unresolved": (
                "no grid carbon intensity was supplied. It varies by country, "
                "season and hour -- roughly tenfold between the cleanest and "
                "dirtiest European grids -- so this project will not assume "
                "one. Supply the figure your grid operator publishes; the kWh "
                "above is what it multiplies."
            ),
        }

    return {
        "grams_co2_per_1k_tokens": round(kwh_per_1k * float(grid_intensity_g_co2_per_kwh), 6),
        "kwh_per_1k_tokens": round(kwh_per_1k, 9),
        "grid_intensity_g_co2_per_kwh": float(grid_intensity_g_co2_per_kwh),
        # The energy is measured; the carbon is arithmetic on someone else's
        # number, and saying so is the difference between a measurement and an
        # estimate presented as one.
        "basis": (
            "measured energy multiplied by a caller-supplied grid intensity; "
            "the energy is measured on this machine, the intensity is not"
        ),
        "unresolved": None,
    }
