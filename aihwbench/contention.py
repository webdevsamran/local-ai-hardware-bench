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

__all__ = ["sample_contention", "BUSY_CPU_PERCENT", "BUSY_GPU_PERCENT", "BUSY_GPU_VRAM_MB"]

#: CPU utilization above which the machine was not idle enough to measure on.
#:
#: Matches the threshold `self-test` has always warned at. A desktop at rest
#: sits in single digits; this leaves room for the ordinary background of a
#: working machine while catching the scan, the build and the other benchmark
#: that make a number meaningless.
BUSY_CPU_PERCENT = 20.0

#: GPU utilization above which the card was not free to be measured.
#:
#: The CPU threshold alone missed the case it most needed to catch. A sweep on
#: this machine returned a 10,395 MiB peak for a configuration whose mirror
#: image -- the same total cache, K and V swapped -- read 764 MiB, because an
#: unrelated image-generation job took the card mid-sweep and held 16 GB at
#: 100% utilization. CPU load stayed unremarkable throughout, so the guard
#: that existed said the machine was idle while the GPU was saturated.
#:
#: Matches the threshold `sample_idle_power` already refuses a power baseline
#: at, for the same reason: a busy card is not a card you are measuring.
BUSY_GPU_PERCENT = 15.0

#: Resident VRAM above which something else is holding the card.
#:
#: A model left loaded by an earlier run, or another process's weights, both
#: change what the next measurement sees -- and unlike utilization, resident
#: memory is high even while the other process is briefly idle.
BUSY_GPU_VRAM_MB = 512.0

#: How long to sample. Long enough not to catch a single scheduling spike,
#: short enough not to lengthen every run noticeably.
_SAMPLE_SECONDS = 0.5


def _sample_gpu() -> dict[str, Any]:
    """What the GPU was doing, alongside the CPU reading.

    Separated so a machine with no readable GPU still gets a CPU verdict: the
    absence of a card is not evidence of contention, and a benchmark on a
    CPU-only machine must not be blocked by it.
    """
    from .telemetry import _nvidia_smi_sample

    sample = _nvidia_smi_sample()
    if sample is None:
        return {
            "gpu_percent": None,
            "gpu_vram_mb": None,
            "gpu_busy": None,
            "gpu_observation": "GPU not readable",
            "gpu_reason": "no readable GPU, so GPU contention was not measured",
        }

    util = sample.get("gpu_util_percent")
    vram = sample.get("vram_mb")
    util_busy = isinstance(util, int | float) and util > BUSY_GPU_PERCENT
    vram_busy = isinstance(vram, int | float) and vram > BUSY_GPU_VRAM_MB
    reasons = []
    if util_busy:
        reasons.append(f"GPU at {util:.0f}% utilization")
    if vram_busy:
        reasons.append(f"{vram:.0f} MB of VRAM already resident")

    observation = " and ".join(reasons)
    return {
        "gpu_percent": round(float(util), 1) if isinstance(util, int | float) else None,
        "gpu_vram_mb": round(float(vram), 1) if isinstance(vram, int | float) else None,
        "gpu_busy": util_busy or vram_busy,
        # The observation on its own, so a caller reporting both processors
        # can join them without repeating the conclusion.
        "gpu_observation": observation or "GPU idle",
        "gpu_reason": (
            f"{observation} before the run: something else is using the card, "
            "and a benchmark against it measures the competition"
            if reasons
            else "GPU idle before the run"
        ),
    }


def sample_contention() -> dict[str, Any]:
    """Machine load immediately before a benchmark begins.

    Sampled *before* the run, because during it the benchmark is itself the
    load and the reading would say nothing.

    Both processors are checked, because a benchmark can be starved by either
    and the CPU reading alone missed the worse case. A sweep on this machine
    returned a 10,395 MB peak for a configuration whose mirror image read 764
    MB, because an unrelated image-generation job took the card mid-sweep and
    held 16 GB at 100% utilization. CPU load stayed unremarkable, so the guard
    reported an idle machine while the GPU was saturated.

    Returns ``busy: None`` when nothing could be measured -- unknown, which is
    a different statement from "the machine was quiet" and must not be
    confused with it.
    """
    gpu = _sample_gpu()

    try:
        import psutil
    except ImportError:
        # No CPU reading, but a GPU reading may still condemn the run. An
        # unreadable CPU is not a reason to ignore a saturated card.
        return {
            "cpu_percent": None,
            "busy": True if gpu["gpu_busy"] else None,
            "threshold_percent": BUSY_CPU_PERCENT,
            "reason": (
                f"psutil is not installed, so CPU load was not measured. {gpu['gpu_reason']}"
            ),
            **gpu,
        }

    try:
        cpu = float(psutil.cpu_percent(interval=_SAMPLE_SECONDS))
    except (OSError, ValueError):  # pragma: no cover - platform dependent
        return {
            "cpu_percent": None,
            "busy": True if gpu["gpu_busy"] else None,
            "threshold_percent": BUSY_CPU_PERCENT,
            "reason": f"CPU utilization could not be read. {gpu['gpu_reason']}",
            **gpu,
        }

    cpu_busy = cpu > BUSY_CPU_PERCENT
    parts = []
    if cpu_busy:
        parts.append(
            f"CPU was at {cpu:.0f}% before the run, above the {BUSY_CPU_PERCENT:.0f}% threshold"
        )
    if gpu["gpu_busy"]:
        # The bare observation, not the full sentence: the shared trailing
        # clause below supplies the "and therefore" once, for both processors.
        parts.append(gpu["gpu_observation"])

    return {
        "cpu_percent": round(cpu, 1),
        "busy": bool(cpu_busy or gpu["gpu_busy"]),
        "threshold_percent": BUSY_CPU_PERCENT,
        "reason": (
            "; ".join(parts) + ": this measures the machine under contention, not the hardware"
            if parts
            else f"CPU at {cpu:.0f}% before the run, {gpu['gpu_reason'].lower()}"
        ),
        **gpu,
    }
