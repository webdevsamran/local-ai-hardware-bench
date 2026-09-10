"""A benchmark measures hardware only when the hardware is available to it.

Found by nearly publishing the mistake. A re-measurement of ONNX Runtime on
CPU reported 2.53 inferences per second where the same model on the same
machine had done 299.92 — a 118x difference caused by an antivirus scan
holding the CPU at 68%. OpenVINO on CPU was 78x slow in the same window, and
the two GPU paths 2.3x slow, because they still need the CPU to feed them.

Every one of those results passed the full data-quality gate. They were
consistent, so variance was low. They were internally coherent, so
plausibility was clean. Nothing in the corpus gave them anything to be
implausible *against*.

`aihwbench self-test` had warned about background load above 20% CPU since
long before any of this. Nothing called it: it was reachable only by someone
who chose to run `self-test` first, which a benchmark in CI or in a
contributor's script never does.
"""

from __future__ import annotations

import pytest

from aihwbench.contention import BUSY_CPU_PERCENT, sample_contention
from aihwbench.quality import data_quality_report


def _patch_cpu(monkeypatch: pytest.MonkeyPatch, percent: float) -> None:
    import psutil

    monkeypatch.setattr(psutil, "cpu_percent", lambda interval=None: percent)


def test_a_quiet_machine_is_not_flagged(monkeypatch):
    _patch_cpu(monkeypatch, 4.0)
    state = sample_contention()
    assert state["busy"] is False
    assert state["cpu_percent"] == 4.0
    assert state["threshold_percent"] == BUSY_CPU_PERCENT


def test_a_busy_machine_is_flagged_with_the_number(monkeypatch):
    """The measured case: 68% CPU from a background scan."""
    _patch_cpu(monkeypatch, 68.0)
    state = sample_contention()
    assert state["busy"] is True
    assert state["cpu_percent"] == 68.0
    assert "under contention" in state["reason"]


def test_load_that_could_not_be_measured_is_unknown_not_quiet(monkeypatch):
    """`busy: None` is a different statement from `busy: False`.

    Refusing to publish for want of an optional dependency would be a worse
    rule than the one it replaced.
    """
    import builtins

    real_import = builtins.__import__

    def no_psutil(name, *args, **kwargs):
        if name == "psutil":
            raise ImportError("psutil unavailable in this test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_psutil)
    state = sample_contention()
    assert state["busy"] is None
    assert state["cpu_percent"] is None
    assert "not installed" in state["reason"]


def _result(contention: dict | None) -> dict:
    repro: dict = {"iterations": 8, "warmup_runs": 3}
    if contention is not None:
        repro["machine_contention"] = contention
    return {
        "schema_version": "2.0",
        "run_id": "r1",
        "timestamp": "2026-01-01T00:00:00Z",
        "system": {"gpu_vram_mb": 16384},
        "runtime": {"name": "onnxruntime", "backend": "x", "device": "cpu"},
        "model": {"name": "m.onnx"},
        "metrics": {"generation_tokens_per_second": 100.0},
        "provenance": {"result_hash": "sha256:abc"},
        "reproducibility": repro,
    }


def test_the_quality_gate_refuses_a_contended_run():
    report = data_quality_report(
        _result({"cpu_percent": 68.0, "busy": True, "threshold_percent": 20.0, "reason": "busy"})
    )
    assert report["checks"]["measured_on_an_idle_machine"] is False
    assert report["checks_passed"] < report["checks_total"]


def test_the_quality_gate_accepts_a_quiet_run():
    report = data_quality_report(
        _result({"cpu_percent": 3.0, "busy": False, "threshold_percent": 20.0, "reason": "idle"})
    )
    assert report["checks"]["measured_on_an_idle_machine"] is True


def test_unknown_load_does_not_fail_the_gate():
    report = data_quality_report(
        _result({"cpu_percent": None, "busy": None, "threshold_percent": 20.0, "reason": "?"})
    )
    assert report["checks"]["measured_on_an_idle_machine"] is True


def test_a_result_predating_the_field_does_not_fail():
    """Older results carry no contention block, and were not measured badly.

    Treating absence as failure would retroactively condemn a corpus this
    knows nothing about.
    """
    report = data_quality_report(_result(None))
    assert report["checks"]["measured_on_an_idle_machine"] is True


def test_the_threshold_matches_what_self_test_has_always_warned_at():
    """One number, so the two do not drift into disagreeing."""
    import inspect

    from aihwbench import selftest

    source = inspect.getsource(selftest._check_background_load)
    assert f"{BUSY_CPU_PERCENT}" in source


def test_published_results_record_what_the_machine_was_doing():
    """Every result produced after this exists carries the block."""
    import glob
    import json

    for path in sorted(glob.glob("results/published/*.json")):
        doc = json.loads(open(path, encoding="utf-8").read())
        repro = doc.get("reproducibility") or {}
        # Results predating the field are exempt; those carrying it must be
        # complete, since a half-filled block is worse than none.
        state = repro.get("machine_contention")
        if state is None:
            continue
        assert "busy" in state, path
        assert "threshold_percent" in state, path
