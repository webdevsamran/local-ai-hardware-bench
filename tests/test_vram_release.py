"""A terminated process is not a released allocation.

The OS reaps a terminated `llama-server` and reports it gone while the driver
is still tearing down its GPU context; a *leaked* server holds its allocation
indefinitely. Both were observed: a stray llama-server sat on 1022 MiB across
an entire sweep, and every point of that sweep would have measured the stray
along with itself.

Nothing in the resulting numbers would have said so. That is the failure mode
this repository keeps finding -- a run contaminated uniformly is a run with
low variance, and low variance reads as a good measurement. It is the shape of
the antivirus scan that produced a 118x error and passed the entire quality
gate.

This guard is deliberately not fatal. When the memory does not come back, the
run that just finished is still worth keeping; it is the next one that is
suspect, and saying so is the difference between a caveat and a silent error.
"""

from __future__ import annotations

import aihwbench.telemetry as telemetry
from aihwbench.telemetry import VRAM_RELEASE_TOLERANCE_MB, wait_for_vram_release


def _readings(monkeypatch, values: list[float | None]) -> list[int]:
    """Feed `current_vram_mb` a fixed sequence; the last value repeats."""
    calls = [0]

    def fake() -> float | None:
        index = min(calls[0], len(values) - 1)
        calls[0] += 1
        return values[index]

    monkeypatch.setattr(telemetry, "current_vram_mb", fake)
    monkeypatch.setattr(telemetry.time, "sleep", lambda _s: None)
    return calls


def test_memory_already_back_returns_at_once(monkeypatch):
    _readings(monkeypatch, [500.0])
    report = wait_for_vram_release(500.0)
    assert report["released"] is True
    assert report["waited_seconds"] < 1.0


def test_it_waits_for_a_lagging_driver_then_succeeds(monkeypatch):
    """The real case: memory comes back a moment after the process is reaped."""
    _readings(monkeypatch, [1800.0, 1800.0, 900.0, 500.0])
    report = wait_for_vram_release(500.0)
    assert report["released"] is True
    assert report["vram_mb"] == 500.0


def test_memory_that_never_comes_back_is_reported_not_raised(monkeypatch):
    """The next measurement is suspect, but this one is over.

    Raising here would discard a completed run to report a problem with the
    *next* one. Saying so is what turns a silent error into a caveat.
    """
    _readings(monkeypatch, [1800.0])
    report = wait_for_vram_release(500.0, timeout=1.0, interval=0.01)
    assert report["released"] is False
    assert report["vram_mb"] == 1800.0
    assert "still resident" in report["reason"]


def test_the_tolerance_absorbs_driver_rounding(monkeypatch):
    """Demanding an exact return would never be satisfied."""
    _readings(monkeypatch, [500.0 + VRAM_RELEASE_TOLERANCE_MB - 1])
    assert wait_for_vram_release(500.0)["released"] is True

    _readings(monkeypatch, [500.0 + VRAM_RELEASE_TOLERANCE_MB + 200])
    assert wait_for_vram_release(500.0, timeout=0.5, interval=0.01)["released"] is False


def test_an_unreadable_baseline_is_unknown_not_released(monkeypatch):
    """A machine with no nvidia-smi must still be able to benchmark.

    `None` says the check could not be made -- which is not the same as
    saying the memory came back, and must not be recorded as if it were.
    """
    report = wait_for_vram_release(None)
    assert report["released"] is None
    assert "nothing to return to" in report["reason"]


def test_vram_becoming_unreadable_mid_wait_is_unknown(monkeypatch):
    _readings(monkeypatch, [1800.0, None])
    report = wait_for_vram_release(500.0, timeout=2.0, interval=0.01)
    assert report["released"] is None
    assert "unreadable" in report["reason"]


def test_the_llama_cpp_handle_waits_on_teardown():
    """The guard has to be *called*, not merely available.

    This repository's recurring defect is a capability that is built, tested,
    exported and never reached by production code.
    """
    import inspect

    from aihwbench.backends import llama_cpp

    teardown = inspect.getsource(llama_cpp.LlamaServerHandle.__exit__)
    assert "wait_for_vram_release" in teardown

    startup = inspect.getsource(llama_cpp.LlamaServerHandle.__enter__)
    assert "current_vram_mb" in startup, "teardown needs a pre-run reading to compare against"
