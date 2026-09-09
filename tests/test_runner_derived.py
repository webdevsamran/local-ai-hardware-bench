"""The runner attaches the derived analyses that had no producer.

`compute_energy_metrics` and the thermal analyzer existed, were tested, and
were marked done in ROADMAP -- but nothing in a benchmark path called either,
and nothing published the telemetry trace they consume. These tests hold the
wiring in place: a capability nothing invokes is not a shipped capability.
"""

from __future__ import annotations

from typing import Any

import pytest

from aihwbench import runner
from tests.test_schemas import make_valid_result


def _fake_backend(result: dict[str, Any]):
    class _Backend:
        @staticmethod
        def run(_config: Any, _system: dict[str, Any]) -> dict[str, Any]:
            return result

    return _Backend


@pytest.fixture
def patched(monkeypatch):
    """Run the real runner against a backend that returns a fixed document."""

    def _install(result: dict[str, Any], idle_watts: float | None = 20.0):
        import aihwbench.backends as backends
        import aihwbench.telemetry as telemetry

        monkeypatch.setattr(backends, "resolve", lambda _name: _fake_backend(result))
        monkeypatch.setattr(runner, "detect_system", lambda: result["system"], raising=False)
        monkeypatch.setattr(
            telemetry,
            "sample_idle_power",
            lambda *_a, **_k: {
                "watts": idle_watts,
                "samples": 4 if idle_watts is not None else 0,
                "source": "nvidia-smi" if idle_watts is not None else None,
            },
        )

    return _install


class _Config:
    # Positive, so the idle sampler runs -- it is monkeypatched, so this costs
    # no wall-clock time. Zero is the documented opt-out and is covered below.
    extra: dict[str, Any] = {"idle_baseline_seconds": 0.01}


class _ConfigNoIdle:
    extra: dict[str, Any] = {"idle_baseline_seconds": 0}


def test_energy_block_is_attached_from_measured_power(patched):
    result = make_valid_result()
    result["metrics"]["average_power_watts"] = 120.0
    result["metrics"]["generation_tokens_per_second"] = 40.0
    patched(result, idle_watts=20.0)

    out = runner.run_benchmark("ollama", _Config())

    energy = out["energy"]
    assert energy["gross_average_power_watts"] == 120.0
    assert energy["idle_baseline_power_watts"] == 20.0
    # Incremental isolates the benchmark's own draw: 120 - 20 = 100 W.
    assert energy["incremental_power_watts"] == 100.0
    # 100 W over 40 tok/s is 2.5 joules per token.
    assert energy["energy_joules_per_token"] == pytest.approx(2.5)


def test_energy_is_null_rather_than_guessed_without_power(patched):
    result = make_valid_result()
    result["metrics"]["average_power_watts"] = None
    patched(result, idle_watts=None)

    energy = runner.run_benchmark("ollama", _Config())["energy"]

    assert energy["incremental_power_watts"] is None
    assert energy["energy_joules_per_token"] is None
    assert energy["measured_inputs"]["average_power_watts"] is False


def test_thermal_block_is_computed_from_the_published_trace(patched):
    result = make_valid_result()
    result["telemetry"] = {
        "source": "aihwbench-telemetry",
        "trace": {
            "series": [{"timestamp": 1000.0 + i, "temperature_c": 70.0 + i} for i in range(20)]
        },
    }
    patched(result)

    thermal = runner.run_benchmark("ollama", _Config())["thermal"]

    assert thermal["throttled"] is True
    assert thermal["time_to_throttle_s"] == 15.0
    assert thermal["max_temperature_c"] == 89.0


def test_thermal_says_so_when_there_is_no_trace(patched):
    """A result with no telemetry must report that, not a fabricated verdict."""
    result = make_valid_result()
    patched(result)

    thermal = runner.run_benchmark("ollama", _Config())["thermal"]

    assert thermal["temperature_slope_c_per_min"] is None
    assert thermal["throttled"] is None


def test_derived_blocks_still_validate(patched):
    """Energy and thermal are declared in the schema, not smuggled through."""
    from aihwbench.formal_schema import validate_formal
    from aihwbench.schemas import validate_result
    from aihwbench.versions import CURRENT_SCHEMA_VERSION

    result = make_valid_result()
    result["schema_version"] = CURRENT_SCHEMA_VERSION
    result["metrics"]["average_power_watts"] = 120.0
    result["telemetry"] = {
        "trace": {"series": [{"timestamp": float(i), "temperature_c": 70.0} for i in range(5)]}
    }
    patched(result)

    out = runner.run_benchmark("ollama", _Config())

    assert validate_result(out) == []
    assert validate_formal(out) == []


def test_idle_sampling_can_be_skipped(patched, monkeypatch):
    """Opting out must yield null figures, never a guessed baseline.

    Measuring the idle draw costs wall-clock time before every run, so it has
    to be skippable; what must not happen is a skipped measurement quietly
    becoming an assumed one.
    """
    import aihwbench.telemetry as telemetry

    called = []
    result = make_valid_result()
    result["metrics"]["average_power_watts"] = 120.0
    patched(result, idle_watts=20.0)
    monkeypatch.setattr(
        telemetry,
        "sample_idle_power",
        lambda *a, **k: called.append(1) or {"watts": 20.0, "samples": 1, "source": "x"},
    )

    energy = runner.run_benchmark("ollama", _ConfigNoIdle())["energy"]

    assert called == [], "idle sampling must not run when opted out"
    assert energy["idle_baseline_power_watts"] is None
    assert energy["incremental_power_watts"] is None
    assert energy["gross_average_power_watts"] == 120.0
