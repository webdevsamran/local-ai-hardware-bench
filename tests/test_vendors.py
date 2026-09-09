"""Vendor telemetry parsers.

Only NVIDIA GPUs supplied power and thermal context; every AMD, Intel and
Apple result carried nulls. Parsing is separated from probing so the parsers
can be verified on any machine while the probes need the hardware.

That split is also the honesty boundary. These tests establish that the
parsers behave; they do not establish that the formats match a real driver,
and `VENDOR_STATUS` says so per vendor.
"""

from __future__ import annotations

import json

import pytest

from aihwbench.vendors import (
    VENDOR_STATUS,
    battery_sample,
    parse_powermetrics,
    parse_rapl_energy,
    parse_rocm_smi,
)

ROCM_JSON = json.dumps(
    {
        "card0": {
            "Card series": "Radeon RX 7900 XTX",
            "GPU use (%)": "78",
            "GPU Memory Allocated (VRAM%)": "41",
            "GPU memory use (MB)": "9820",
            "Temperature (Sensor edge) (C)": "62.0",
            "Temperature (Sensor junction) (C)": "78.0",
            "Average Graphics Package Power (W)": "221.0",
        }
    }
)


# ------------------------------------------------------------------ AMD


def test_rocm_reads_the_documented_fields():
    sample = parse_rocm_smi(ROCM_JSON)
    assert sample is not None
    assert sample["gpu_util_percent"] == 78.0
    assert sample["temperature_c"] == 62.0
    assert sample["power_watts"] == 221.0
    assert sample["gpu_device_name"] == "Radeon RX 7900 XTX"
    assert sample["telemetry_vendor"] == "amd"


def test_rocm_does_not_read_a_percentage_as_megabytes():
    """ROCm reports both 'memory use (MB)' and 'Memory Allocated (VRAM%)'.

    Matching on the word 'memory' alone picked up whichever came first, which
    would report 41 MB of VRAM in use on a card holding 9.8 GB. Wrong data is
    worse than missing data, so the unit is part of the match.
    """
    sample = parse_rocm_smi(ROCM_JSON)
    assert sample is not None
    assert sample["vram_mb"] == 9820.0
    assert sample["vram_percent"] == 41.0


def test_rocm_prefers_the_edge_temperature_sensor():
    """Junction runs hotter; picking one and naming it beats averaging."""
    sample = parse_rocm_smi(ROCM_JSON)
    assert sample is not None
    assert sample["temperature_c"] == 62.0


@pytest.mark.parametrize(
    "payload", ["", "not json", "[]", "null", json.dumps({"system": {"driver": "x"}})]
)
def test_rocm_returns_nothing_for_unrecognised_output(payload):
    """An unrecognised format must yield no sample, never a guess."""
    assert parse_rocm_smi(payload) is None


# ---------------------------------------------------------------- Apple


def test_powermetrics_prefers_the_combined_package_figure():
    payload = "CPU Power: 4210 mW\nGPU Power: 8800 mW\nCombined Power (CPU + GPU + ANE): 14100 mW\n"
    sample = parse_powermetrics(payload)
    assert sample is not None
    assert sample["power_watts"] == 14.1
    assert sample["power_basis"] == "package"


def test_powermetrics_falls_back_to_cpu_plus_gpu_and_says_so():
    sample = parse_powermetrics("CPU Power: 4210 mW\nGPU Power: 8800 mW\n")
    assert sample is not None
    assert sample["power_watts"] == 13.01
    assert sample["power_basis"] == "cpu+gpu", "a fallback must be labelled as one"


@pytest.mark.parametrize("payload", ["", "   ", "no power lines here"])
def test_powermetrics_returns_nothing_without_power_lines(payload):
    assert parse_powermetrics(payload) is None


# ---------------------------------------------------------------- Intel


def test_rapl_converts_an_energy_delta_to_average_power():
    """RAPL counts joules, not watts; power only exists over an interval."""
    # 30 J over 0.5 s is 60 W.
    sample = parse_rapl_energy(1_000_000, 31_000_000, 0.5)
    assert sample is not None
    assert sample["power_watts"] == 60.0
    assert sample["energy_joules"] == 30.0
    assert sample["counter_wrapped"] is False


def test_rapl_corrects_a_wrapped_counter():
    sample = parse_rapl_energy(9_000_000, 100_000, 0.5, max_energy_uj=10_000_000)
    assert sample is not None
    assert sample["counter_wrapped"] is True
    # (10.0 - 9.0 + 0.1) J over 0.5 s.
    assert sample["power_watts"] == pytest.approx(2.2)


def test_rapl_refuses_a_wrap_it_cannot_correct():
    """Without the wrap point, the delta is unknowable -- not negative power."""
    assert parse_rapl_energy(9_000_000, 100_000, 0.5) is None


@pytest.mark.parametrize(
    ("start", "end", "elapsed"),
    [(None, 1.0, 0.5), (1.0, None, 0.5), (1.0, 2.0, 0.0), (1.0, 2.0, -1.0)],
)
def test_rapl_returns_nothing_for_unusable_inputs(start, end, elapsed):
    assert parse_rapl_energy(start, end, elapsed) is None


def test_rapl_states_that_it_excludes_a_discrete_gpu():
    """A CPU-package figure read as whole-system power would mislead badly."""
    sample = parse_rapl_energy(0, 1_000_000, 1.0)
    assert sample is not None
    assert "excludes a discrete GPU" in sample["scope"]


# --------------------------------------------------------------- battery


def test_battery_sample_is_shaped_correctly_or_absent():
    """Desktops have no battery; that is absence, not failure."""
    sample = battery_sample()
    if sample is None:
        pytest.skip("no battery on this machine")
    assert 0.0 <= sample["battery_percent"] <= 100.0
    assert isinstance(sample["on_ac_power"], bool)
    left = sample["battery_seconds_left"]
    assert left is None or left >= 0, "psutil sentinels must not leak as durations"


def test_vendor_status_is_declared_for_every_collector():
    """Support must be stated, not inferred from a function existing."""
    for vendor in ("nvidia", "amd", "intel", "apple", "battery"):
        assert VENDOR_STATUS[vendor]


def test_unverified_vendors_say_so():
    """The same honesty the compatibility matrix applies to backends."""
    for vendor in ("amd", "intel", "apple"):
        assert "not run on real hardware" in VENDOR_STATUS[vendor] or (
            "not read on real hardware" in VENDOR_STATUS[vendor]
        )
