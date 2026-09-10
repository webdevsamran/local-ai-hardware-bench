"""Performance regression detection between a baseline and a candidate.

Compares two schema-valid results that are STRICTLY or CONDITIONALLY
comparable, applying configurable thresholds per metric family:

- throughput (generation tok/s): candidate must not drop more than X%
- ttft_ms: candidate must not increase more than X ms or Y%
- latency (p95): candidate must not increase more than X%
- memory (peak_ram_mb / peak_vram_mb): absolute + percent budget
- power (average_power_watts): absolute + percent budget

Returns a machine-readable verdict suitable for CI gates. Missing
metrics on either side are reported as SKIPPED, never guessed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .comparability import NOT_COMPARABLE, compare_classification


@dataclass
class RegressionThresholds:
    """Configurable thresholds; None disables a check."""

    throughput_max_regression_pct: float | None = 10.0
    ttft_max_increase_ms: float | None = 250.0
    ttft_max_increase_pct: float | None = 50.0
    latency_p95_max_regression_pct: float | None = 25.0
    memory_max_increase_mb: float | None = 1024.0
    memory_max_increase_pct: float | None = 50.0
    power_max_increase_watts: float | None = 15.0
    power_max_increase_pct: float | None = 50.0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RegressionThresholds:
        valid = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in valid})


@dataclass
class MetricCheck:
    metric: str
    direction: str  # "lower_is_better" | "higher_is_better"
    baseline: float | None
    candidate: float | None
    delta: float | None
    delta_pct: float | None
    status: str  # PASS | FAIL | SKIPPED | INFORMATIONAL
    reason: str = ""


@dataclass
class RegressionReport:
    classification: str
    status: str  # PASS | FAIL | INCOMPARABLE
    checks: list[MetricCheck] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "classification": self.classification,
            "status": self.status,
            "checks": [c.__dict__ for c in self.checks],
            "failures": self.failures,
        }


def _pct(baseline: float, candidate: float) -> float:
    return (candidate - baseline) / abs(baseline) * 100.0 if baseline else 0.0


def _check(
    name: str,
    direction: str,
    base_val: float | None,
    cand_val: float | None,
    limit_abs: float | None,
    limit_pct: float | None,
) -> MetricCheck:
    """Evaluate one metric against absolute and/or percent thresholds."""
    if base_val is None or cand_val is None:
        return MetricCheck(
            name, direction, base_val, cand_val, None, None, "SKIPPED", "metric missing on one side"
        )
    delta = round(cand_val - base_val, 3)
    delta_pct = round(_pct(base_val, cand_val), 2)
    worse_abs = (
        limit_abs is not None
        and abs(delta) > limit_abs
        and (
            (direction == "lower_is_better" and delta > 0)
            or (direction == "higher_is_better" and delta < 0)
        )
    )
    worse_pct = (
        limit_pct is not None
        and abs(delta_pct) > limit_pct
        and (
            (direction == "lower_is_better" and delta_pct > 0)
            or (direction == "higher_is_better" and delta_pct < 0)
        )
    )
    if worse_abs or worse_pct:
        reason_bits = []
        if worse_abs and limit_abs is not None:
            reason_bits.append(f"|delta|={abs(delta)} > {limit_abs}")
        if worse_pct and limit_pct is not None:
            reason_bits.append(f"|delta%|={abs(delta_pct)} > {limit_pct}")
        return MetricCheck(
            name, direction, base_val, cand_val, delta, delta_pct, "FAIL", "; ".join(reason_bits)
        )
    return MetricCheck(name, direction, base_val, cand_val, delta, delta_pct, "PASS")


#: Telemetry field behind each regression metric, for scope lookups.
_METRIC_TELEMETRY_FIELD = {
    "peak_ram_mb": "ram_mb",
    "peak_vram_mb": "vram_mb",
    "average_power_watts": "power_watts",
}


def _system_scoped_metrics(*results: dict[str, Any]) -> set[str]:
    """Regression metrics either result declares as system-wide.

    Read from the results rather than hardcoded, because scope depends on how
    a given machine measured: `power_watts` is device-scoped from nvidia-smi
    and CPU-package-scoped from RAPL, and a future sampler could report
    process RAM instead of system RAM. The document says which; this asks it.
    """
    scoped: set[str] = set()
    for result in results:
        telemetry = result.get("telemetry")
        if not isinstance(telemetry, dict):
            continue
        scope = telemetry.get("scope")
        if not isinstance(scope, dict):
            continue
        for metric, field_name in _METRIC_TELEMETRY_FIELD.items():
            if scope.get(field_name) == "system":
                scoped.add(metric)
    return scoped


def _demote_if_system_scoped(check: MetricCheck, system_scoped: set[str]) -> MetricCheck:
    """Turn a failure on a machine-wide metric into an observation.

    The delta is kept: a large jump in system memory is worth seeing, and
    might even be the benchmark's doing. What it cannot do is decide a gate,
    because nothing here can attribute it to the run.
    """
    if check.metric not in system_scoped or check.status not in ("FAIL", "PASS"):
        return check
    reason = check.reason
    note = "measured system-wide, so a delta cannot be attributed to this run; reported, not gated"
    return MetricCheck(
        check.metric,
        check.direction,
        check.baseline,
        check.candidate,
        check.delta,
        check.delta_pct,
        "INFORMATIONAL",
        f"{reason}; {note}" if reason else note,
    )


def evaluate_regression(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    thresholds: RegressionThresholds | None = None,
    *,
    force: bool = False,
) -> RegressionReport:
    """Compare candidate against baseline under the given thresholds.

    When the pair is NOT_COMPARABLE the verdict is ``INCOMPARABLE`` and no
    checks run: a threshold comparison between two different experiments
    measures nothing. Callers must treat that as a failed gate, not a pass —
    ``aihwbench regression`` exits ``EXIT_NOT_COMPARABLE`` for it.

    ``force=True`` runs the checks anyway for an operator who has accepted
    that risk. The classification is still reported verbatim, so a forced
    run can never be mistaken for a comparable one.
    """
    t = thresholds or RegressionThresholds()
    classification = compare_classification(baseline, candidate)["classification"]
    if classification == NOT_COMPARABLE and not force:
        return RegressionReport(classification=classification, status="INCOMPARABLE")

    bm = baseline.get("metrics", {})
    cm = candidate.get("metrics", {})

    # Metrics the result itself declares as measuring the whole machine rather
    # than this run. `peak_ram_mb` comes from `psutil.virtual_memory` and is
    # published with `telemetry.scope.ram_mb == "system"`, so a delta between
    # two runs is the difference in what the machine was doing -- a browser
    # tab, an indexer, an antivirus sweep -- not a change in the benchmark.
    #
    # Two runs of the same configuration minutes apart on the reference
    # machine differed by 1.3 GB and failed the gate. A CI gate that fires on
    # someone opening a browser is one people learn to ignore, which costs
    # more than the check was ever worth. These are reported with their deltas
    # and excluded from the verdict.
    system_scoped = _system_scoped_metrics(baseline, candidate)
    checks = [
        _check(
            "generation_tokens_per_second",
            "higher_is_better",
            bm.get("generation_tokens_per_second"),
            cm.get("generation_tokens_per_second"),
            None,
            t.throughput_max_regression_pct,
        ),
        _check(
            "ttft_ms",
            "lower_is_better",
            bm.get("ttft_ms"),
            cm.get("ttft_ms"),
            t.ttft_max_increase_ms,
            t.ttft_max_increase_pct,
        ),
        _check(
            "p95_latency_ms",
            "lower_is_better",
            bm.get("p95_latency_ms"),
            cm.get("p95_latency_ms"),
            None,
            t.latency_p95_max_regression_pct,
        ),
        _check(
            "peak_ram_mb",
            "lower_is_better",
            bm.get("peak_ram_mb"),
            cm.get("peak_ram_mb"),
            t.memory_max_increase_mb,
            t.memory_max_increase_pct,
        ),
        _check(
            "peak_vram_mb",
            "lower_is_better",
            bm.get("peak_vram_mb"),
            cm.get("peak_vram_mb"),
            t.memory_max_increase_mb,
            t.memory_max_increase_pct,
        ),
        _check(
            "average_power_watts",
            "lower_is_better",
            bm.get("average_power_watts"),
            cm.get("average_power_watts"),
            t.power_max_increase_watts,
            t.power_max_increase_pct,
        ),
    ]
    checks = [_demote_if_system_scoped(c, system_scoped) for c in checks]
    failures = [f"{c.metric}: {c.reason}" for c in checks if c.status == "FAIL"]
    status = "FAIL" if failures else "PASS"
    return RegressionReport(
        classification=classification, status=status, checks=checks, failures=failures
    )
