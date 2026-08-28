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
        assert set(sample) == _SAMPLE_KEYS
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
