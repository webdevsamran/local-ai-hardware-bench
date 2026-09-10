"""Tests for baseline/regression primitives."""

from __future__ import annotations

from aihwbench.comparability import NOT_COMPARABLE
from aihwbench.regression import (
    RegressionThresholds,
    evaluate_regression,
)
from tests.test_ecosystem import _result


def test_pass_when_candidate_within_thresholds():
    base = _result("base", 100.0)
    cand = _result("cand", 95.0)  # 5% slower, within 10% budget
    report = evaluate_regression(base, cand)
    assert report.status == "PASS"
    assert report.failures == []


def test_fail_on_throughput_regression():
    base = _result("base", 100.0)
    cand = _result("cand", 80.0)  # 20% drop > 10% budget
    report = evaluate_regression(base, cand)
    assert report.status == "FAIL"
    assert any("generation_tokens_per_second" in f for f in report.failures)


def test_fail_on_ttft_increase():
    base = _result("base", 100.0)
    cand = _result("cand", 100.0)
    cand["metrics"]["ttft_ms"] = base["metrics"]["ttft_ms"] + 1000.0
    report = evaluate_regression(base, cand)
    assert report.status == "FAIL"
    assert any("ttft_ms" in f for f in report.failures)


def test_missing_metrics_are_skipped_not_failed():
    base = _result("base", 100.0)
    cand = _result("cand", 100.0)
    base["metrics"]["average_power_watts"] = None
    cand["metrics"]["average_power_watts"] = None
    report = evaluate_regression(base, cand)
    power = next(c for c in report.checks if c.metric == "average_power_watts")
    assert power.status == "SKIPPED"
    assert report.status == "PASS"


def test_incomparable_results_reported():
    base = _result("base", 100.0)
    cand = _result("cand", 100.0)
    cand["runtime"]["name"] = "llama.cpp"
    report = evaluate_regression(base, cand)
    assert report.status == "INCOMPARABLE"


def test_custom_thresholds_via_from_dict():
    t = RegressionThresholds.from_dict({"throughput_max_regression_pct": 1.0})
    base = _result("base", 100.0)
    cand = _result("cand", 98.0)  # 2% drop, fails 1% budget
    report = evaluate_regression(base, cand, t)
    assert report.status == "FAIL"


def test_machine_readable_output_shape():
    base = _result("base", 100.0)
    cand = _result("cand", 95.0)
    d = evaluate_regression(base, cand).to_dict()
    assert d["status"] in ("PASS", "FAIL", "INCOMPARABLE")
    assert isinstance(d["checks"], list)
    assert all("metric" in c and "status" in c for c in d["checks"])


# --------------------------------------------------------------- fail-closed
#
# A regression gate that reports success when it ran zero checks is worse than
# no gate: it fails open exactly when the environment drifted, which is when it
# is most needed. These tests hold the gate closed.


def test_incomparable_runs_no_checks():
    """INCOMPARABLE must mean 'nothing was measured', not 'nothing was wrong'."""
    base = _result("base", 100.0)
    cand = _result("cand", 1.0)  # 100x slower
    cand["runtime"]["name"] = "llama.cpp"
    report = evaluate_regression(base, cand)
    assert report.status == "INCOMPARABLE"
    assert report.checks == []


def test_force_runs_the_checks_and_catches_the_regression():
    """--force is an override of comparability, not of the thresholds."""
    base = _result("base", 100.0)
    cand = _result("cand", 1.0)
    cand["runtime"]["name"] = "llama.cpp"
    report = evaluate_regression(base, cand, force=True)
    assert report.status == "FAIL"
    assert report.checks, "forcing must actually evaluate the metrics"
    assert any("generation_tokens_per_second" in f for f in report.failures)


def test_force_still_reports_the_true_classification():
    """A forced run must never be mistakable for a comparable one."""
    base = _result("base", 100.0)
    cand = _result("cand", 100.0)
    cand["runtime"]["name"] = "llama.cpp"
    report = evaluate_regression(base, cand, force=True)
    assert report.classification == NOT_COMPARABLE


# --- A machine-wide metric cannot decide a gate about one run ---------------
#
# `peak_ram_mb` comes from `psutil.virtual_memory` and every result publishes
# it with `telemetry.scope.ram_mb == "system"`. Two runs of the same
# configuration, minutes apart on the reference machine, differed by 1.3 GB
# and failed the gate — the difference being what else the desktop was doing.
# A CI gate that fires when someone opens a browser is one people learn to
# ignore, which costs more than the check was worth.


def _with_scope(result: dict, **scope) -> dict:
    result = dict(result)
    result["telemetry"] = {"scope": scope}
    return result


def test_system_scoped_memory_is_reported_but_does_not_fail_the_gate():
    base = _with_scope(_result("base", 100.0), ram_mb="system", vram_mb="device")
    cand = _with_scope(_result("cand", 100.0), ram_mb="system", vram_mb="device")
    base["metrics"]["peak_ram_mb"] = 16000.0
    cand["metrics"]["peak_ram_mb"] = 18000.0  # +2 GB of unrelated desktop use

    report = evaluate_regression(base, cand)
    ram = next(c for c in report.checks if c.metric == "peak_ram_mb")
    assert ram.status == "INFORMATIONAL"
    # The delta is still visible; only the verdict is withheld.
    assert ram.delta == 2000.0
    assert "cannot be attributed to this run" in ram.reason
    assert report.status == "PASS"
    assert report.failures == []


def test_device_scoped_memory_still_gates():
    """VRAM is the benchmark's own footprint, and a jump there is real."""
    base = _with_scope(_result("base", 100.0), ram_mb="system", vram_mb="device")
    cand = _with_scope(_result("cand", 100.0), ram_mb="system", vram_mb="device")
    base["metrics"]["peak_vram_mb"] = 600.0
    cand["metrics"]["peak_vram_mb"] = 4000.0

    report = evaluate_regression(base, cand)
    assert report.status == "FAIL"
    assert any("peak_vram_mb" in f for f in report.failures)


def test_scope_is_read_from_the_result_not_hardcoded():
    """A sampler that measured process RAM would make the metric gateable.

    Scope depends on how a machine measured: power is device-scoped from
    nvidia-smi and CPU-package-scoped from RAPL. The document says which, so
    the checker asks it rather than assuming.
    """
    base = _with_scope(_result("base", 100.0), ram_mb="process")
    cand = _with_scope(_result("cand", 100.0), ram_mb="process")
    base["metrics"]["peak_ram_mb"] = 1000.0
    cand["metrics"]["peak_ram_mb"] = 9000.0

    report = evaluate_regression(base, cand)
    ram = next(c for c in report.checks if c.metric == "peak_ram_mb")
    assert ram.status == "FAIL"
    assert report.status == "FAIL"


def test_a_result_without_telemetry_scope_still_gates():
    """Absent scope must not silently disable a check.

    Older results carry no scope block, and treating "unknown" as "system"
    would quietly stop gating memory for the whole existing corpus.
    """
    base = _result("base", 100.0)
    cand = _result("cand", 100.0)
    base["metrics"]["peak_ram_mb"] = 1000.0
    cand["metrics"]["peak_ram_mb"] = 9000.0

    report = evaluate_regression(base, cand)
    assert report.status == "FAIL"


def test_a_real_regression_still_fails_alongside_an_informational_metric():
    """The demotion must not swallow the verdict it sits next to."""
    base = _with_scope(_result("base", 300.0), ram_mb="system")
    cand = _with_scope(_result("cand", 30.0), ram_mb="system")  # 10x slower
    base["metrics"]["peak_ram_mb"] = 16000.0
    cand["metrics"]["peak_ram_mb"] = 18000.0

    report = evaluate_regression(base, cand)
    assert report.status == "FAIL"
    assert any("generation_tokens_per_second" in f for f in report.failures)
    assert not any("peak_ram_mb" in f for f in report.failures)
