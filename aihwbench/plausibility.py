"""Implausible-value detection for submitted results.

The moment a leaderboard matters to anyone, someone will try to top it. This
module is the cheap half of defending against that, and it is deliberately the
*uncontroversial* half.

It checks two kinds of thing:

- **Impossible values.** A run cannot use more VRAM than the card has, a
  utilisation cannot exceed 100%, a first token cannot arrive after the last
  one. These need no assumption about what hardware is capable of, so they can
  never be argued with — which is exactly what an integrity check should be.
- **Internal inconsistency.** Percentiles that are out of order, or an
  energy-per-token figure that does not follow from the power and throughput
  reported beside it. A result that contradicts itself was either
  mis-measured or assembled by hand.

It deliberately does **not** guess performance ceilings per hardware class.
"A 3080 Ti cannot exceed N tok/s" is a claim about hardware that this project
has not measured across the range, and a false accusation is far more damaging
than a missed one. Statistical outliers are already caught by
``quality.flag_anomalies``, which compares like with like against a cohort
rather than against a number someone guessed.

Findings are **review requests, never fraud verdicts** -- the same contract
the anomaly flags carry, and the reason the dispute process exists.
"""

from __future__ import annotations

from typing import Any

__all__ = ["check_plausibility", "PlausibilityFinding"]

#: Percentile metrics that must be non-decreasing in this order.
_PERCENTILE_ORDER = (
    "p50_latency_ms",
    "p90_latency_ms",
    "p95_latency_ms",
    "p99_latency_ms",
)

#: Metrics that are physically non-negative. A negative value is a bug in the
#: producer, not a fast machine.
_NON_NEGATIVE = (
    "ttft_ms",
    "total_latency_ms",
    "load_time_ms",
    "generation_tokens_per_second",
    "prompt_tokens_per_second",
    "peak_ram_mb",
    "peak_vram_mb",
    "average_power_watts",
    "idle_power_watts",
    "energy_joules_per_token",
)

#: Silicon does not operate here. Well outside any real reading, so a genuine
#: hot laptop is never flagged.
_MIN_TEMPERATURE_C = -40.0
_MAX_TEMPERATURE_C = 150.0

#: How far a derived energy figure may drift from power/throughput before it
#: is treated as inconsistent rather than rounded.
_ENERGY_TOLERANCE = 0.10

#: How far idle power may exceed average power under load before it counts as
#: inconsistent rather than as sensor drift.
#:
#: A workload that barely touches the GPU makes "average under load" almost
#: another idle sample, and two idle samples on a laptop dGPU differ by a few
#: percent as fans, clocks and temperature move. Measured case: a 0.5B model
#: held an RTX 3080 Ti at ~6% utilization, giving 28.26 W under load against a
#: 29.62 W baseline -- a 4.6% excess that this check called inconsistent.
#:
#: The condition worth flagging is the structural one the check was written
#: for: readings taken against different things, or swapped. Those are not off
#: by a few percent. Nothing is hidden by tolerating drift here -- the energy
#: block already withholds per-token energy and states why whenever the
#: workload's draw cannot be resolved above the baseline.
_IDLE_EXCESS_TOLERANCE = 0.10


class PlausibilityFinding(dict[str, Any]):
    """One finding: a field, what is wrong, and why that is impossible."""


def _finding(field: str, value: Any, detail: str, kind: str) -> PlausibilityFinding:
    return PlausibilityFinding(
        field=field,
        value=value,
        kind=kind,
        detail=detail,
        action="manual_review",
    )


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def check_plausibility(result: dict[str, Any]) -> list[PlausibilityFinding]:
    """Findings for one result. An empty list means nothing impossible.

    Every finding is a review request. None of them asserts bad faith: the
    overwhelmingly likely cause of an impossible value is a measurement or
    reporting bug, which is worth finding for its own sake.
    """
    findings: list[PlausibilityFinding] = []
    metrics = result.get("metrics") or {}
    system = result.get("system") or {}

    for field in _NON_NEGATIVE:
        value = _number(metrics.get(field))
        if value is not None and value < 0:
            findings.append(
                _finding(f"metrics.{field}", value, "negative value is impossible", "impossible")
            )

    for field in ("avg_cpu_util_percent", "avg_gpu_util_percent"):
        value = _number(metrics.get(field))
        if value is not None and not 0.0 <= value <= 100.0:
            findings.append(
                _finding(f"metrics.{field}", value, "utilisation outside 0-100%", "impossible")
            )

    temperature = _number(metrics.get("max_temperature_c"))
    if temperature is not None and not _MIN_TEMPERATURE_C <= temperature <= _MAX_TEMPERATURE_C:
        findings.append(
            _finding(
                "metrics.max_temperature_c",
                temperature,
                f"outside {_MIN_TEMPERATURE_C}-{_MAX_TEMPERATURE_C} C; silicon does not run here",
                "impossible",
            )
        )

    # A run cannot occupy more VRAM than the card reports having.
    peak_vram = _number(metrics.get("peak_vram_mb"))
    total_vram = _number(system.get("gpu_vram_mb"))
    if peak_vram is not None and total_vram is not None and total_vram > 0:
        if peak_vram > total_vram:
            findings.append(
                _finding(
                    "metrics.peak_vram_mb",
                    peak_vram,
                    f"exceeds the {total_vram:.0f} MB the GPU reports having",
                    "impossible",
                )
            )

    # The first token cannot arrive after the last one.
    ttft = _number(metrics.get("ttft_ms"))
    total = _number(metrics.get("total_latency_ms"))
    if ttft is not None and total is not None and ttft > total:
        findings.append(
            _finding(
                "metrics.ttft_ms",
                ttft,
                f"time to first token exceeds total latency ({total} ms)",
                "impossible",
            )
        )

    # Percentiles are non-decreasing by construction.
    previous_name: str | None = None
    previous_value: float | None = None
    for name in _PERCENTILE_ORDER:
        value = _number(metrics.get(name))
        if value is None:
            continue
        if previous_value is not None and value < previous_value:
            findings.append(
                _finding(
                    f"metrics.{name}",
                    value,
                    f"below {previous_name} ({previous_value}); percentiles cannot decrease",
                    "inconsistent",
                )
            )
        previous_name, previous_value = name, value

    # Idle power well above average power under load means the two were
    # measured against different things, or swapped. A few percent is drift;
    # see _IDLE_EXCESS_TOLERANCE.
    idle = _number(metrics.get("idle_power_watts"))
    average = _number(metrics.get("average_power_watts"))
    if idle is not None and average is not None and average > 0:
        excess = (idle - average) / average
        if excess > _IDLE_EXCESS_TOLERANCE:
            findings.append(
                _finding(
                    "metrics.idle_power_watts",
                    idle,
                    (
                        f"idle draw exceeds the {average} W average under load by "
                        f"{excess:.0%}, beyond the {_IDLE_EXCESS_TOLERANCE:.0%} "
                        "attributable to sensor drift"
                    ),
                    "inconsistent",
                )
            )

    # Energy per token must follow from the power it claims to be derived from.
    #
    # This read `metrics.energy_joules_per_token`, which is null in every
    # result ever published -- the field was computed before power was
    # measured -- so the check has never once run. It reads the `energy`
    # block now, where the figure actually lives, and against the same
    # incremental power the block used to compute it. Checking it against
    # *gross* power, as the old code did, would have flagged every correct
    # result the moment the field started carrying a value.
    energy_block = result.get("energy") or {}
    energy = _number(energy_block.get("energy_joules_per_token"))
    incremental = _number(energy_block.get("incremental_power_watts"))
    throughput = _number(metrics.get("generation_tokens_per_second"))
    if energy is not None and incremental is not None and throughput and throughput > 0:
        expected = incremental / throughput
        if expected > 0 and abs(energy - expected) / expected > _ENERGY_TOLERANCE:
            findings.append(
                _finding(
                    "energy.energy_joules_per_token",
                    energy,
                    (
                        f"does not follow from {incremental} W incremental at "
                        f"{throughput} tok/s (expected about {expected:.4f})"
                    ),
                    "inconsistent",
                )
            )

    return findings
