"""What else the machine was doing when a benchmark started.

A benchmark measures hardware only when the hardware is available to it. This
was found the hard way: a re-measurement of ONNX Runtime on CPU reported 2.53
inferences per second against 299.92 from the same model on the same machine
weeks earlier -- a 118x difference caused by an antivirus scan holding the CPU
at 68%. The result passed every data-quality check. It was consistent, so
variance was low; it was internally coherent, so plausibility was clean; and
nothing in the corpus gave it anything to be implausible *against*.

`aihwbench self-test` has warned about background load since long before that,
at CPU above 20%. Nothing called it: it was reachable only by a person who
chose to run `self-test` first, and a benchmark that runs unattended in CI or
from a contributor's script never did.

So the state is recorded on every run, at the same moment as the idle power
baseline and for the same reason -- both describe the machine the measurement
was taken on, and neither can be reconstructed afterwards.
"""

from __future__ import annotations

from typing import Any

__all__ = ["sample_contention", "BUSY_CPU_PERCENT"]

#: CPU utilization above which the machine was not idle enough to measure on.
#:
#: Matches the threshold `self-test` has always warned at. A desktop at rest
#: sits in single digits; this leaves room for the ordinary background of a
#: working machine while catching the scan, the build and the other benchmark
#: that make a number meaningless.
BUSY_CPU_PERCENT = 20.0

#: How long to sample. Long enough not to catch a single scheduling spike,
#: short enough not to lengthen every run noticeably.
_SAMPLE_SECONDS = 0.5


def sample_contention() -> dict[str, Any]:
    """Machine load immediately before a benchmark begins.

    Sampled *before* the run, because during it the benchmark is itself the
    load and the reading would say nothing.

    Returns ``busy: None`` when psutil is unavailable -- unknown, which is a
    different statement from "the machine was quiet" and must not be confused
    with it.
    """
    try:
        import psutil
    except ImportError:
        return {
            "cpu_percent": None,
            "busy": None,
            "threshold_percent": BUSY_CPU_PERCENT,
            "reason": "psutil is not installed, so machine load was not measured",
        }

    try:
        cpu = float(psutil.cpu_percent(interval=_SAMPLE_SECONDS))
    except (OSError, ValueError):  # pragma: no cover - platform dependent
        return {
            "cpu_percent": None,
            "busy": None,
            "threshold_percent": BUSY_CPU_PERCENT,
            "reason": "CPU utilization could not be read",
        }

    busy = cpu > BUSY_CPU_PERCENT
    return {
        "cpu_percent": round(cpu, 1),
        "busy": busy,
        "threshold_percent": BUSY_CPU_PERCENT,
        "reason": (
            f"CPU was at {cpu:.0f}% before the run, above the "
            f"{BUSY_CPU_PERCENT:.0f}% threshold: this measures the machine "
            "under contention, not the hardware"
            if busy
            else f"CPU at {cpu:.0f}% before the run"
        ),
    }
