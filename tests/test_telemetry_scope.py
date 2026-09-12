"""Phase-A regression tests: telemetry scope/source/device provenance.

Covers the audited defects:

1. The no-psutil Windows fallback called ``ctypes.windll`` without a
   platform guard, breaking non-Windows platforms.
2. Telemetry fields could read like generic metrics without stating
   scope (system vs device), source (psutil / Windows API / nvidia-smi),
   or which device was actually sampled.

Tests are hermetic: sampling functions are monkeypatched, no GPU or
psutil availability is required.
"""

from __future__ import annotations

import platform
import sys
import threading

import pytest

import aihwbench.telemetry as tlm
from aihwbench.telemetry import TelemetrySampler, measure

_SAMPLE_KEYS = {
    "timestamp",
    "ram_mb",
    "cpu_util_percent",
    "vram_mb",
    "gpu_util_percent",
    "temperature_c",
    "power_watts",
    "gpu_device_index",
    "gpu_device_name",
}

# Present only on a machine with a battery, which most desktops are not. The
# sample shape is therefore the base keys plus these, never these alone.
_BATTERY_KEYS = {"battery_percent", "on_ac_power", "battery_seconds_left"}


def _synthetic_gpu() -> dict:
    return {
        "vram_mb": 16384.0,
        "gpu_util_percent": 42.0,
        "temperature_c": 61.0,
        "power_watts": 26.5,
        "gpu_device_index": "0",
        "gpu_device_name": "Synthetic GPU",
    }


def _run_sampler(monkeypatch, gpu_fn) -> TelemetrySampler:
    monkeypatch.setattr(tlm, "_system_ram_sample", lambda: (8192.0, "test-ram"))
    monkeypatch.setattr(tlm, "_cpu_util_sample", lambda: (37.5, "test-cpu"))
    monkeypatch.setattr(tlm, "_nvidia_smi_sample", gpu_fn)
    sampler = TelemetrySampler(interval_seconds=0.02)
    sampler.start()
    import time as _time

    _time.sleep(0.09)
    sampler.stop()
    return sampler


def test_summary_values_come_from_samples(monkeypatch):
    sampler = _run_sampler(monkeypatch, _synthetic_gpu)
    s = sampler.summary()
    assert s["peak_ram_mb"] == 8192.0
    assert s["avg_cpu_util_percent"] == 37.5
    assert s["peak_vram_mb"] == 16384.0
    assert s["avg_gpu_util_percent"] == 42.0
    assert s["max_temperature_c"] == 61.0
    assert s["average_power_watts"] == 26.5


def test_provenance_declares_scope_sources_device(monkeypatch):
    sampler = _run_sampler(monkeypatch, _synthetic_gpu)
    prov = sampler.provenance()
    assert prov["samples"] > 0
    assert prov["interval_seconds"] == 0.02
    assert prov["source"] == "aihwbench-telemetry"
    # Scope: RAM/CPU are system-wide; GPU metrics belong to one device.
    assert prov["scope"]["ram_mb"] == "system"
    assert prov["scope"]["cpu_util_percent"] == "system"
    assert prov["scope"]["power_watts"] == "device"
    # Sources name the measurement mechanism per metric.
    assert prov["sources"]["ram_mb"] == "test-ram"
    assert prov["sources"]["cpu_util_percent"] == "test-cpu"
    for key in ("vram_mb", "gpu_util_percent", "temperature_c", "power_watts"):
        assert prov["sources"][key] == "nvidia-smi"
    # The actually-sampled device is identified.
    assert prov["device"] == {"gpu_device_index": "0", "gpu_device_name": "Synthetic GPU"}


def test_provenance_without_gpu_has_no_device_claim(monkeypatch):
    sampler = _run_sampler(monkeypatch, lambda: None)
    prov = sampler.provenance()
    assert "device" not in prov
    for key in ("vram_mb", "gpu_util_percent", "temperature_c", "power_watts"):
        assert prov["sources"][key] is None
    s = sampler.summary()
    assert s["peak_vram_mb"] is None
    assert s["average_power_watts"] is None


def test_raw_trace_timestamped_and_complete(monkeypatch):
    sampler = _run_sampler(monkeypatch, _synthetic_gpu)
    trace = sampler.raw_trace()
    assert len(trace) == sampler.provenance()["samples"]
    timestamps = [s["timestamp"] for s in trace]
    assert timestamps == sorted(timestamps)
    for sample in trace:
        assert set(sample) - _BATTERY_KEYS == _SAMPLE_KEYS
        assert sample["timestamp"] > 0


def test_summary_before_start_is_all_none():
    s = TelemetrySampler(interval_seconds=0.01).summary()
    assert set(s) == {
        "peak_ram_mb",
        "peak_vram_mb",
        "avg_cpu_util_percent",
        "avg_gpu_util_percent",
        "max_temperature_c",
        "average_power_watts",
    }
    assert all(v is None for v in s.values())


def test_measure_helper():
    value, elapsed_ms = measure(lambda: 7)
    assert value == 7
    assert elapsed_ms >= 0.0


def test_windows_ram_fallback_guarded_by_platform(monkeypatch):
    """Without psutil, the ctypes.windll fallback must run only on
    Windows; other platforms fail soft to (None, None) without raising
    (audited defect: previously raised AttributeError on Linux)."""
    monkeypatch.setitem(sys.modules, "psutil", None)  # force ImportError
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    assert tlm._system_ram_sample() == (None, None)


@pytest.mark.skipif(platform.system() != "Windows", reason="Windows API fallback")
def test_windows_ram_fallback_works_on_windows(monkeypatch):
    monkeypatch.setitem(sys.modules, "psutil", None)  # force fallback path
    value, source = tlm._system_ram_sample()
    assert source == "windows-globalmemorystatus"
    assert value is None or value > 0.0


# --- The idle baseline must describe an idle machine -------------------------
#
# `sample_idle_power` used to average whatever the power sensor reported in the
# window before load, with no check that the machine was idle. A busy GPU then
# became the "baseline", and subtracting it made the benchmark look more
# efficient than it was. Separately, a card still holding a model from an
# earlier run idles far higher than the same card after eviction -- so the
# state the baseline was taken in has to travel with it.


def _idle_sampler(monkeypatch, *, watts, util, vram=0.0):
    """Patch the GPU sampler to report fixed readings, and skip the sleeps."""
    import aihwbench.telemetry as tlm

    monkeypatch.setattr(
        tlm,
        "_nvidia_smi_sample",
        lambda: {
            "power_watts": watts,
            "gpu_util_percent": util,
            "vram_mb": vram,
            "temperature_c": 40.0,
            "gpu_device_index": "0",
            "gpu_device_name": "Test GPU",
        },
    )
    monkeypatch.setattr(tlm.time, "sleep", lambda _seconds: None)
    return tlm


def test_idle_baseline_is_refused_when_the_gpu_is_busy(monkeypatch):
    tlm = _idle_sampler(monkeypatch, watts=210.0, util=94.0)
    baseline = tlm.sample_idle_power(seconds=0.01, interval=0.0)

    assert baseline["quiescent"] is False
    # Fail closed: no baseline beats one that flatters the benchmark.
    assert baseline["watts"] is None
    # Kept for diagnosis under its own name, where nothing will subtract it.
    assert baseline["observed_watts"] == 210.0
    assert "utilization" in baseline["reason"]


def test_a_refused_baseline_yields_no_incremental_figure(monkeypatch):
    """The guard is only worth having if it reaches the published numbers."""
    from aihwbench.analysis.energy import compute_energy_metrics

    tlm = _idle_sampler(monkeypatch, watts=210.0, util=94.0)
    baseline = tlm.sample_idle_power(seconds=0.01, interval=0.0)
    out = compute_energy_metrics(
        average_power_watts=220.0,
        idle_power_watts=baseline["watts"],
        generation_tokens_per_second=40.0,
        requests_per_second=None,
    )
    assert out["incremental_power_watts"] is None
    assert out["energy_joules_per_token"] is None
    assert out["incremental_is_robust"] is None


def test_idle_baseline_is_kept_when_the_gpu_is_quiet(monkeypatch):
    tlm = _idle_sampler(monkeypatch, watts=14.9, util=1.0)
    baseline = tlm.sample_idle_power(seconds=0.01, interval=0.0)

    assert baseline["quiescent"] is True
    assert baseline["watts"] == 14.9
    assert baseline["reason"] is None
    assert "observed_watts" not in baseline


def test_idle_baseline_records_resident_vram(monkeypatch):
    """What explains two honest baselines disagreeing by 2x on one machine."""
    tlm = _idle_sampler(monkeypatch, watts=31.41, util=2.0, vram=632.0)
    baseline = tlm.sample_idle_power(seconds=0.01, interval=0.0)

    assert baseline["quiescent"] is True  # low utilization: genuinely at rest
    assert baseline["watts"] == 31.41
    # ...but not at rest in the same *state*, and the result says so.
    assert baseline["resident_vram_mb"] == 632.0


def test_no_power_sensor_reports_why(monkeypatch):
    import aihwbench.telemetry as tlm

    monkeypatch.setattr(tlm, "_nvidia_smi_sample", lambda: None)
    monkeypatch.setattr(tlm.time, "sleep", lambda _seconds: None)
    baseline = tlm.sample_idle_power(seconds=0.01, interval=0.0)

    assert baseline["watts"] is None
    assert baseline["samples"] == 0
    assert baseline["quiescent"] is None  # unknown, not "not idle"
    assert baseline["reason"]


# --- CPU-package power as the last resort ------------------------------------
#
# `rapl_power_sample` existed, was correct, and nothing ever called it. On a
# machine with no discrete GPU -- most consumer laptops -- no other probe
# reports power, so those runs carried no energy data at all and the
# joules-per-token figures the project treats as a differentiator existed only
# for people who already owned an NVIDIA card.
#
# The sampler cannot call `rapl_power_sample` directly: it sleeps to obtain
# its second counter reading, which would double the sampling interval.


class _FakeCounter:
    """A RAPL sysfs counter that advances by a fixed energy each read."""

    def __init__(self, step_uj: float, *, start: float = 0.0, maximum: float = 1_000_000.0):
        self.value = start
        self.step_uj = step_uj
        self.maximum = maximum

    def __call__(self, path: str) -> float | None:
        if path.endswith("max_energy_range_uj"):
            return self.maximum
        current = self.value
        self.value += self.step_uj
        return current


def test_rapl_reader_needs_two_readings_before_reporting(monkeypatch):
    import aihwbench.telemetry as tlm

    monkeypatch.setattr(tlm, "read_rapl_counter", _FakeCounter(step_uj=5_000_000.0))
    monkeypatch.setattr(tlm.time, "monotonic", _clock())

    reader = tlm.RaplPowerReader()
    # A cumulative counter says nothing until it is read twice.
    assert reader.sample() is None
    second = reader.sample()
    assert second is not None
    assert second["power_watts"] > 0


def _clock(step: float = 1.0):
    """A monotonic clock that advances a fixed amount per call."""
    state = {"t": 0.0}

    def now() -> float:
        state["t"] += step
        return state["t"]

    return now


def test_rapl_reader_derives_power_from_the_delta(monkeypatch):
    import aihwbench.telemetry as tlm

    # 5 J per second-long tick is 5 W.
    monkeypatch.setattr(tlm, "read_rapl_counter", _FakeCounter(step_uj=5_000_000.0))
    monkeypatch.setattr(tlm.time, "monotonic", _clock(step=1.0))

    reader = tlm.RaplPowerReader()
    reader.sample()
    sample = reader.sample()
    assert sample["power_watts"] == pytest.approx(5.0, abs=0.01)
    assert sample["telemetry_vendor"] == "intel"
    # The narrower scope travels with the reading, so it can never be
    # mistaken for whole-system or GPU power.
    assert "excludes a discrete GPU" in sample["scope"]


def test_rapl_reader_is_unavailable_without_the_counter(monkeypatch):
    import aihwbench.telemetry as tlm

    monkeypatch.setattr(tlm, "read_rapl_counter", lambda path: None)
    reader = tlm.RaplPowerReader()
    assert reader.available() is False
    assert reader.sample() is None


def test_idle_baseline_falls_back_to_rapl(monkeypatch):
    """Otherwise a GPU-less machine measures load power against no baseline."""
    import aihwbench.telemetry as tlm

    monkeypatch.setattr(tlm, "_nvidia_smi_sample", lambda: None)
    monkeypatch.setattr(tlm, "read_rapl_counter", _FakeCounter(step_uj=7_000_000.0))
    monkeypatch.setattr(tlm.time, "monotonic", _clock(step=1.0))
    monkeypatch.setattr(tlm.time, "sleep", lambda _seconds: None)

    # Two ticks of the wall clock, so the sampling window closes.
    times = iter([0.0, 0.5, 1.0, 99.0])
    monkeypatch.setattr(tlm.time, "time", lambda: next(times, 99.0))

    baseline = tlm.sample_idle_power(seconds=1.0, interval=0.0)
    assert baseline["source"] == "intel-rapl"
    assert baseline["watts"] == pytest.approx(7.0, abs=0.01)


def test_gpu_power_is_preferred_over_rapl(monkeypatch):
    """RAPL is a fallback, not a peer: it excludes the discrete GPU."""
    import aihwbench.telemetry as tlm

    monkeypatch.setattr(
        tlm,
        "_nvidia_smi_sample",
        lambda: {
            "power_watts": 180.0,
            "gpu_util_percent": 0.0,
            "vram_mb": 0.0,
            "temperature_c": 40.0,
            "gpu_device_index": "0",
            "gpu_device_name": "Test GPU",
        },
    )
    monkeypatch.setattr(tlm, "read_rapl_counter", _FakeCounter(step_uj=7_000_000.0))
    monkeypatch.setattr(tlm.time, "sleep", lambda _seconds: None)
    times = iter([0.0, 0.5, 99.0])
    monkeypatch.setattr(tlm.time, "time", lambda: next(times, 99.0))

    baseline = tlm.sample_idle_power(seconds=1.0, interval=0.0)
    assert baseline["source"] == "nvidia-smi"
    assert baseline["watts"] == pytest.approx(180.0)


def test_sampler_labels_rapl_power_as_cpu_package(monkeypatch):
    """A CPU-package reading published as "device" invites a false comparison.

    GPU power and CPU-package power are different quantities. The scope map
    was a fixed table saying `power_watts` is always "device"; it now depends
    on which source actually answered.
    """
    import aihwbench.telemetry as tlm

    monkeypatch.setattr(tlm, "_gpu_probes", lambda: ())
    monkeypatch.setattr(tlm, "read_rapl_counter", _FakeCounter(step_uj=6_000_000.0))
    monkeypatch.setattr(tlm.time, "monotonic", _clock(step=1.0))

    sampler = tlm.TelemetrySampler(interval_seconds=0.01)
    sampler.start()
    try:
        _wait_for_samples(sampler)
    finally:
        sampler.stop()

    provenance = sampler.provenance()
    assert provenance["sources"]["power_watts"] == "intel-rapl"
    assert provenance["scope"]["power_watts"] == "cpu-package"
    # Fields that did come from a device keep their scope.
    assert provenance["scope"]["vram_mb"] == "device"


def _wait_for_samples(sampler, minimum: int = 2, timeout: float = 5.0) -> None:
    """Block until the sampler has collected samples, or give up."""
    import time as _time

    deadline = _time.time() + timeout
    while _time.time() < deadline:
        if sampler.provenance()["samples"] >= minimum:
            return
        _time.sleep(0.02)
    raise AssertionError("sampler produced no samples")


def test_the_npu_capability_is_probed_before_the_sampling_thread_starts(monkeypatch):
    """The expensive probe must not sit inside a sampling interval.

    `_npu_probe_enabled` is cached, and its docstring said it was "asked once,
    before a run" -- while actually being asked from `_loop`, on the first
    iteration. On Windows that probe spawns PowerShell, which takes longer
    than one sampling interval and, on a loaded runner, longer than `stop`
    will wait. The sample is appended only after enrichment, so the first
    sample -- RAM and CPU already read -- was discarded and a Windows
    benchmark lost its telemetry at the moment a run began.

    Asserted structurally rather than by timing: a timing test passes against
    the broken code whenever the probe happens to finish inside `stop`'s join
    window, which is most of the time and none of the interesting time. What
    must hold is that the probe has already run, on the calling thread, by the
    time `start` returns.
    """
    threads: list[str] = []
    sampler = TelemetrySampler(interval_seconds=0.02)

    def record_probe() -> bool:
        threads.append(threading.current_thread().name)
        return False

    monkeypatch.setattr(sampler, "_npu_probe_enabled", record_probe)
    monkeypatch.setattr(tlm, "_system_ram_sample", lambda: (8192.0, "test-ram"))
    monkeypatch.setattr(tlm, "_cpu_util_sample", lambda: (37.5, "test-cpu"))
    monkeypatch.setattr(tlm, "_nvidia_smi_sample", lambda: None)

    caller = threading.current_thread().name
    sampler.start()
    probed_during_start = list(threads)
    try:
        assert probed_during_start, (
            "start() returned without resolving the NPU capability: the probe "
            "is back inside the sampling loop, where it costs the first sample"
        )
        assert probed_during_start[0] == caller, (
            f"the probe ran on {probed_during_start[0]!r}, not on the calling "
            f"thread {caller!r} -- it is being resolved from the sampling loop"
        )
    finally:
        sampler.stop()
