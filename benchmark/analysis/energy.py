"""Energy metrics (#24, #25).

Computes joules/request, joules/token, and joules/1k tokens from measured
average power and throughput, plus gross vs incremental power when an
idle baseline was measured. Every output records its telemetry source and
measurement tier; missing inputs yield None, never estimates.
"""

from __future__ import annotations

from typing import Any

__all__ = ["compute_energy_metrics"]


def compute_energy_metrics(
    average_power_watts: float | None,
    idle_power_watts: float | None,
    generation_tokens_per_second: float | None,
    requests_per_second: float | None,
    telemetry_source: str | None = None,
) -> dict[str, Any]:
    """Derive energy-per-unit metrics from measured power.

    ``telemetry_source`` (e.g. "nvidia-smi", "rapl", "external-meter") is
    echoed into the result so consumers know the measurement tier.
    """
    incremental_watts: float | None = None
    if average_power_watts is not None and idle_power_watts is not None:
        incremental_watts = max(0.0, average_power_watts - idle_power_watts)

    def per_rate(watts: float | None, rate: float | None) -> float | None:
        if watts is None or rate is None or rate <= 0:
            return None
        return watts / rate

    j_per_token = per_rate(incremental_watts, generation_tokens_per_second)
    j_per_request = per_rate(incremental_watts, requests_per_second)
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
        "telemetry_source": telemetry_source,
        "measured_inputs": {
            "average_power_watts": average_power_watts is not None,
            "idle_power_watts": idle_power_watts is not None,
            "generation_tokens_per_second": generation_tokens_per_second is not None,
            "requests_per_second": requests_per_second is not None,
        },
    }
