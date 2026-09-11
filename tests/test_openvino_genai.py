"""OpenVINO GenAI: the decisions that make a result interpretable.

This backend was detection-only until it could measure something. The tests
here cover the parts that decide whether a measured result means anything, and
every one of them runs without OpenVINO installed — CI has no Intel runtime, and
a test suite that skips itself on the machine where it matters is not a gate.

Measured on the reference machine (i9-12900H, Iris Xe, RTX 3080 Ti Laptop) with
`OpenVINO/Qwen2.5-Coder-0.5B-Instruct-int4-ov`: the CPU and the integrated GPU
came back indistinguishable — 74.98 tok/s against 75.97, intervals overlapping
almost entirely — while greedy decoding on the iGPU produced four different
answers from six runs.

An earlier pass of the same sweep, taken while two unrelated test suites were
running, appeared to show the CPU 15% ahead, and that number reached a docstring
here before the controlled run replaced it. Recorded because it is the failure
mode this whole project is about: a plausible ordering, measured under
contention, that would have been written up as a finding.
"""

from __future__ import annotations

import pytest

from aihwbench.backends import openvino_genai as backend
from aihwbench.backends.base import BackendError, BenchmarkConfig, RuntimeStatus

VISIBLE = ["CPU", "GPU.0", "GPU.1", "NPU"]


# --- device resolution ------------------------------------------------------


def test_auto_is_refused_because_the_result_could_not_say_what_ran():
    """OpenVINO's AUTO plugin does not report the device it chose.

    `LLMPipeline` exposes no compiled model, so the choice is unobservable.
    `runtime.device` is in the comparison-safety classifier's strict set, which
    means a guessed value here does not stay local: the classifier would go on
    to call a silently-CPU run comparable with a GPU one.
    """
    with pytest.raises(BackendError) as err:
        backend.resolve_device("auto", VISIBLE)
    message = str(err.value)
    # The error has to be actionable, not merely correct.
    assert "CPU" in message and "GPU.0" in message
    assert "--device" in message


def test_an_empty_device_is_refused_the_same_way():
    with pytest.raises(BackendError):
        backend.resolve_device("", VISIBLE)


@pytest.mark.parametrize(
    "requested,expected",
    [
        ("cpu", "CPU"),
        ("CPU", "CPU"),
        ("npu", "NPU"),
        ("igpu", "GPU.0"),
        ("gpu.1", "GPU.1"),
        ("GPU.0", "GPU.0"),
    ],
)
def test_device_aliases_resolve(requested, expected):
    assert backend.resolve_device(requested, VISIBLE) == expected


def test_a_device_that_is_not_there_is_an_error_not_a_fallback():
    """Falling back to CPU would produce a result labelled NPU."""
    with pytest.raises(BackendError) as err:
        backend.resolve_device("npu", ["CPU"])
    assert "not visible" in str(err.value)


def test_bare_gpu_is_allowed_when_numbered_gpus_exist():
    """OpenVINO resolves bare GPU to GPU.0 itself; refusing would be pedantry."""
    assert backend.resolve_device("gpu", ["CPU", "GPU.0", "GPU.1"]) == "GPU"


# --- telemetry that belongs to a different device ---------------------------


def test_gpu_metrics_are_dropped_when_they_describe_another_gpu():
    """The sampler reads nvidia-smi whatever the run was on.

    For a run on an Intel iGPU that yields `peak_vram_mb: 0.0` — a true
    statement about an idle NVIDIA card, and one that reads as "this run used
    no graphics memory". The iGPU allocates from shared system RAM, which
    nvidia-smi cannot see at all. Unmeasured is not zero.
    """
    metrics = {"peak_vram_mb": 0.0, "avg_gpu_util_percent": 0.0, "ttft_ms": 58.8}
    out = backend.disown_foreign_gpu_metrics(
        metrics,
        ran_on="Intel(R) Iris(R) Xe Graphics (iGPU)",
        sampled="NVIDIA GeForce RTX 3080 Ti Laptop GPU",
    )
    assert out["peak_vram_mb"] is None
    assert out["avg_gpu_util_percent"] is None
    # The measurement that does belong to this run is untouched.
    assert out["ttft_ms"] == 58.8
    note = out["metric_source"]["gpu_telemetry_note"]
    assert "Iris" in note and "NVIDIA" in note


def test_gpu_metrics_are_kept_when_the_sampled_device_is_the_one_that_ran():
    """Dropping them here would throw away the real measurement."""
    metrics = {"peak_vram_mb": 1022.0, "avg_gpu_util_percent": 94.0}
    out = backend.disown_foreign_gpu_metrics(
        metrics,
        ran_on="NVIDIA GeForce RTX 3080 Ti Laptop GPU (dGPU)",
        sampled="NVIDIA GeForce RTX 3080 Ti Laptop GPU",
    )
    assert out["peak_vram_mb"] == 1022.0
    assert out["avg_gpu_util_percent"] == 94.0
    assert "metric_source" not in out


def test_device_names_are_compared_loosely_enough_to_match():
    """OpenVINO appends "(dGPU)" where nvidia-smi does not.

    An equality test would call one card two devices and throw away every GPU
    measurement the project takes.
    """
    assert backend._normalise_device_name(
        "NVIDIA GeForce RTX 3080 Ti Laptop GPU (dGPU)"
    ) == backend._normalise_device_name("NVIDIA GeForce RTX 3080 Ti Laptop GPU")


def test_an_unnamed_device_does_not_silently_match_an_unnamed_sample():
    """Two unknowns are not a match; they are two unknowns."""
    out = backend.disown_foreign_gpu_metrics(
        {"peak_vram_mb": 0.0}, ran_on="Intel(R) Iris(R) Xe Graphics", sampled=None
    )
    assert out["peak_vram_mb"] is None


# --- the model directory ----------------------------------------------------


def test_a_missing_model_directory_names_a_flag_that_exists(tmp_path):
    """An error telling someone to pass `--model-dir` would be a dead end:
    the CLI has no such flag."""
    config = BenchmarkConfig(model="", extra={})
    with pytest.raises(BackendError) as err:
        backend._require_model_dir(config)
    assert "--model-path" in str(err.value)


def test_a_directory_without_an_ir_is_rejected(tmp_path):
    config = BenchmarkConfig(model=str(tmp_path), extra={})
    with pytest.raises(BackendError) as err:
        backend._require_model_dir(config)
    assert "openvino_model.xml" in str(err.value)


def test_pointing_at_the_xml_resolves_to_its_directory(tmp_path):
    """The obvious mistake, and free to handle."""
    (tmp_path / "openvino_model.xml").write_text("<net/>", encoding="utf-8")
    config = BenchmarkConfig(model="m", extra={"model_path": str(tmp_path / "openvino_model.xml")})
    assert backend._require_model_dir(config) == tmp_path


def test_model_dir_takes_precedence_over_model_path(tmp_path):
    ir = tmp_path / "ir"
    ir.mkdir()
    (ir / "openvino_model.xml").write_text("<net/>", encoding="utf-8")
    config = BenchmarkConfig(model="m", extra={"model_dir": str(ir), "model_path": "/nowhere"})
    assert backend._require_model_dir(config) == ir


# --- refusing to invent results ---------------------------------------------


def test_run_raises_rather_than_fabricating_when_unavailable(monkeypatch):
    """A backend that returns plausible numbers when its runtime is missing is
    worse than one that errors, because the numbers get published."""
    monkeypatch.setattr(backend, "_import_openvino_genai", lambda: None)
    config = BenchmarkConfig(model="m", device="cpu")
    with pytest.raises(BackendError) as err:
        backend.run(config, {})
    assert "not runnable" in str(err.value)


def test_detection_says_which_half_is_missing(monkeypatch):
    """ "Unavailable" does not tell anyone what to install."""
    monkeypatch.setattr(backend, "_import_openvino_genai", lambda: None)
    info = backend.detect()
    assert info.status is RuntimeStatus.CONFIGURATION_REQUIRED
    assert "pip install openvino-genai" in (info.detail or "")

    monkeypatch.setattr(backend, "_import_openvino_genai", lambda: object())
    monkeypatch.setattr(backend, "_detect_devices", lambda: [])
    info = backend.detect()
    assert info.status is RuntimeStatus.HARDWARE_REQUIRED


def test_pipelines_are_reused_per_model_and_device(tmp_path):
    """Compiling an IR costs 2 seconds on CPU and 17 on a discrete GPU.

    An agentic workload calls `generate_text` once per turn. Rebuilding each
    time would leave the backend nominally able to run those workloads and far
    too slow to use — a capability nobody can reach, which is this
    repository's most common way of shipping nothing.
    """
    built: list[tuple[str, str]] = []

    class FakeGenai:
        @staticmethod
        def LLMPipeline(model_dir: str, device: str) -> object:  # noqa: N802 - mirrors the API
            built.append((model_dir, device))
            return object()

    backend._PIPELINE_CACHE.clear()
    first = backend._pipeline_for(FakeGenai, tmp_path, "CPU")
    second = backend._pipeline_for(FakeGenai, tmp_path, "CPU")
    assert first is second
    assert len(built) == 1

    # A different device is a different compilation and must not be shared.
    other = backend._pipeline_for(FakeGenai, tmp_path, "GPU.0")
    assert other is not first
    assert len(built) == 2
    backend._PIPELINE_CACHE.clear()


def test_the_backend_is_registered():
    from aihwbench.backends import BACKENDS, resolve

    assert "openvino_genai" in BACKENDS
    module = resolve("openvino_genai")
    assert callable(module.run)
    assert callable(module.detect)
