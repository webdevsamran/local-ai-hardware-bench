"""Backends for hardware nobody here has, tested without it.

Nine backends could detect their runtime and then refused to measure anything:
ROCm, QNN, Hailo, TensorRT, Lemonade, ExLlamaV2, MLX, WebGPU, Windows ML. Each
said "planned" and raised. That is honest, and it is also the state in which
code rots fastest — nothing exercises it, so nothing catches it decaying, and
the person who finally plugs in a Radeon card discovers the backend was never
finished rather than never *verified*.

They are written now. Most of them delegate: Vulkan, SYCL and ROCm are build
variants of llama.cpp, QNN and TensorRT and DirectML are execution providers of
ONNX Runtime, Lemonade speaks the OpenAI protocol three other backends already
speak. Only Hailo, ExLlamaV2 and MLX need loops of their own.

**What these tests can and cannot establish.** They cannot prove a Snapdragon
NPU produces a good number; nobody here has one. They can prove the dispatch
picks the right provider, that a missing accelerator is refused rather than
silently replaced by a CPU, that a delegated result says what produced it, and
that a device name is never assumed. Those are the parts that would be wrong on
arrival, and they are testable on any machine.

The one path that *was* exercised on real hardware is the ONNX Runtime
accelerator path, via DirectML on the reference laptop: 101 of 104 MobileNetV2
nodes on the GPU, 3 on the CPU. QNN and TensorRT take that identical code.
"""

from __future__ import annotations

import pytest

from aihwbench.backends import (
    _delegate,
    exllamav2,
    hailo,
    lemonade,
    mlx,
    qnn,
    rocm,
    tensorrt,
    webgpu,
    windows_ml,
)
from aihwbench.backends import (
    onnxruntime as ort_backend,
)
from aihwbench.backends.base import BackendError, BenchmarkConfig, RuntimeStatus

#: Every backend whose hardware is absent here. `run()` must refuse cleanly.
HARDWARE_ABSENT = [rocm, qnn, hailo, tensorrt, lemonade, exllamav2, mlx, webgpu]


# --- nothing fabricates a result --------------------------------------------


@pytest.mark.parametrize("backend", HARDWARE_ABSENT, ids=lambda m: m.__name__.rsplit(".", 1)[-1])
def test_absent_hardware_refuses_rather_than_measuring(backend):
    """The failure that matters most, and the cheapest one to get wrong.

    A backend that returns plausible numbers when its accelerator is missing
    does not merely mislead the person running it: `runtime.name` is in the
    comparison-safety classifier's strict set, so the fabricated row is then
    ranked against real ones.
    """
    config = BenchmarkConfig(model="whatever", extra={"model_path": "nonexistent.onnx"})
    with pytest.raises(BackendError):
        backend.run(config, {})


@pytest.mark.parametrize("backend", HARDWARE_ABSENT, ids=lambda m: m.__name__.rsplit(".", 1)[-1])
def test_detection_never_raises(backend):
    """Detection runs on every `aihwbench doctor`, on machines with anything."""
    info = backend.detect()
    assert isinstance(info.status, RuntimeStatus)


@pytest.mark.parametrize("backend", HARDWARE_ABSENT, ids=lambda m: m.__name__.rsplit(".", 1)[-1])
def test_refusals_say_what_to_install(backend):
    """ "Not available" sends someone to check their hardware. Naming the
    missing package sends them to a fix."""
    config = BenchmarkConfig(model="whatever")
    with pytest.raises(BackendError) as err:
        backend.run(config, {})
    message = str(err.value).lower()
    assert any(
        hint in message
        for hint in ("install", "pip", "build", "requires", "needs", "compiled", "not available")
    ), f"unhelpful refusal: {err.value}"


# --- delegation records what actually ran -----------------------------------


def test_a_delegated_result_says_what_produced_it():
    """A row labelled `rocm` was produced by llama.cpp's HIP build, not by some
    separate AMD runtime, and a reader deciding what the number means needs to
    be able to tell."""
    result = _delegate.relabel(
        {"runtime": {"name": "llama.cpp", "backend": "llama.cpp-server", "device": "cuda"}},
        name="rocm",
        backend="llama.cpp-hip",
        delegated_to="llama.cpp",
        device="ROCm0",
    )
    assert result["runtime"]["name"] == "rocm"
    assert result["runtime"]["backend"] == "llama.cpp-hip"
    assert result["runtime"]["delegated_to"] == "llama.cpp"
    assert result["runtime"]["device"] == "ROCm0"


def test_relabelling_is_what_keeps_two_compute_paths_apart():
    """llama.cpp on Vulkan and llama.cpp on CUDA run different kernels with
    different numerics. `runtime.name` is in the classifier's strict set, so
    leaving both as "llama.cpp" would make them strictly comparable."""
    cuda = _delegate.relabel(
        {"runtime": {}}, name="llama.cpp", backend="llama.cpp-server", delegated_to="llama.cpp"
    )
    vulkan_result = _delegate.relabel(
        {"runtime": {}}, name="vulkan", backend="llama.cpp-vulkan", delegated_to="llama.cpp"
    )
    assert cuda["runtime"]["name"] != vulkan_result["runtime"]["name"]


def test_caller_supplied_extras_win_over_the_delegate():
    """A sweep that pinned gpu_layers means it."""
    config = BenchmarkConfig(model="m", extra={"gpu_layers": 12})
    merged = _delegate.with_extra(config, gpu_layers=99, device="ROCm0")
    assert merged.extra["gpu_layers"] == 12
    assert merged.extra["device"] == "ROCm0"


# --- a device is discovered, never assumed ----------------------------------


def test_the_device_comes_from_the_binarys_own_enumeration(monkeypatch):
    """Hardcoding `Vulkan0` assumes the build has the backend and that its
    first device is the wanted one. The first assumption is the one that
    fails."""
    monkeypatch.setattr(
        "aihwbench.devices.device_inventory",
        lambda **kw: {"devices": [{"id": "CUDA0"}, {"id": "Vulkan1"}], "unresolved": None},
    )
    config = BenchmarkConfig(model="m")
    assert _delegate.require_llama_device("Vulkan", "vulkan", config) == "Vulkan1"


def test_a_backend_with_no_device_refuses_and_lists_what_is_there(monkeypatch):
    """ "Your hardware can, your build cannot" is actionable; "not available"
    is not."""
    monkeypatch.setattr(
        "aihwbench.devices.device_inventory",
        lambda **kw: {"devices": [{"id": "CUDA0"}], "unresolved": None},
    )
    config = BenchmarkConfig(model="m")
    with pytest.raises(BackendError) as err:
        _delegate.require_llama_device("ROCm", "rocm", config)
    assert "CUDA0" in str(err.value)


def test_a_caller_cannot_point_one_backend_at_another_backends_device(monkeypatch):
    """The one place the caller does not simply win.

    `--device CUDA0` through the ROCm backend would measure CUDA and label the
    result `rocm` — the same mislabelling by a more deliberate route.
    """
    config = BenchmarkConfig(model="m", extra={"device": "CUDA0"})
    with pytest.raises(BackendError) as err:
        _delegate.require_llama_device("ROCm", "rocm", config)
    assert "CUDA0" in str(err.value)


def test_a_matching_caller_device_is_honoured(monkeypatch):
    config = BenchmarkConfig(model="m", extra={"device": "ROCm1"})
    assert _delegate.require_llama_device("ROCm", "rocm", config) == "ROCm1"


# --- llama.cpp actually applies the device ----------------------------------


def test_llama_cpp_reads_the_device_key():
    """It did not, for as long as Vulkan and SYCL had been setting it."""
    from aihwbench.backends.llama_cpp import _offload_device

    assert _offload_device(BenchmarkConfig(model="m", extra={"device": "Vulkan0"})) == "Vulkan0"
    assert _offload_device(BenchmarkConfig(model="m")) is None


def test_llama_cpp_passes_the_device_to_the_server():
    """Reading the key and not passing it on would be the same bug again."""
    import inspect

    from aihwbench.backends import llama_cpp

    source = inspect.getsource(llama_cpp)
    assert '"--device"' in source, "the device flag never reaches llama-server"


# --- ONNX Runtime provider selection ----------------------------------------


@pytest.mark.parametrize(
    "device,provider",
    [
        ("qnn", "QNNExecutionProvider"),
        ("tensorrt", "TensorrtExecutionProvider"),
        ("dml", "DmlExecutionProvider"),
        ("rocm", "ROCMExecutionProvider"),
        ("coreml", "CoreMLExecutionProvider"),
    ],
)
def test_each_accelerator_maps_to_its_provider(device, provider, monkeypatch):
    monkeypatch.setattr(ort_backend, "_available_providers", lambda: [provider, "CPU"])
    assert ort_backend._providers_for_device(device)[0] == provider


def test_a_missing_provider_names_the_package_to_install(monkeypatch):
    monkeypatch.setattr(ort_backend, "_available_providers", lambda: ["CPUExecutionProvider"])
    with pytest.raises(BackendError) as err:
        ort_backend._providers_for_device("qnn")
    assert "onnxruntime-qnn" in str(err.value)


def test_an_unknown_device_lists_the_ones_that_exist(monkeypatch):
    monkeypatch.setattr(ort_backend, "_available_providers", lambda: ["CPUExecutionProvider"])
    with pytest.raises(BackendError) as err:
        ort_backend._providers_for_device("banana")
    assert "qnn" in str(err.value) and "cpu" in str(err.value)


def test_cpu_is_a_fallback_for_operators_not_for_a_missing_accelerator(monkeypatch):
    """The CPU provider trailing an accelerator is how ONNX Runtime handles a
    node the accelerator cannot run. It is not permission to run the whole
    model there."""
    monkeypatch.setattr(
        ort_backend, "_available_providers", lambda: ["QNNExecutionProvider", "CPU"]
    )
    assert ort_backend._providers_for_device("qnn") == [
        "QNNExecutionProvider",
        "CPUExecutionProvider",
    ]


# --- the node-assignment probe ----------------------------------------------


def test_node_assignment_counts_per_provider(tmp_path, monkeypatch):
    """Parsed from the trace ONNX Runtime writes; verified against a real
    DirectML session on the reference machine, which reported 101 GPU nodes
    and 3 CPU nodes for MobileNetV2."""
    import json

    profile = tmp_path / "profile.json"
    profile.write_text(
        json.dumps(
            [
                {"cat": "Node", "args": {"provider": "QNNExecutionProvider"}},
                {"cat": "Node", "args": {"provider": "QNNExecutionProvider"}},
                {"cat": "Node", "args": {"provider": "CPUExecutionProvider"}},
                {"cat": "Session", "args": {}},
                {"cat": "Node", "args": {}},
            ]
        ),
        encoding="utf-8",
    )

    class FakeMeta:
        # A declared input, because `resolve_input_specs` refuses a model with
        # none -- rightly: a feed cannot be built for a graph that takes
        # nothing, and a fake without one tests a path that cannot occur.
        name = "input"
        type = "tensor(float)"
        shape = [1, 3, 224, 224]

    class FakeSession:
        def get_outputs(self):
            return []

        def get_inputs(self):
            return [FakeMeta()]

        def run(self, *a, **k):
            return []

        def end_profiling(self):
            return str(profile)

    class FakeORT:
        SessionOptions = type("Options", (), {"enable_profiling": False})

        @staticmethod
        def InferenceSession(*a, **k):  # noqa: N802 - mirrors the real API
            return FakeSession()

    monkeypatch.setitem(__import__("sys").modules, "onnxruntime", FakeORT)
    counts = ort_backend.node_assignment(str(tmp_path / "m.onnx"), ["QNNExecutionProvider"])
    assert counts == {"QNNExecutionProvider": 2, "CPUExecutionProvider": 1}


def test_an_unreadable_trace_is_unknown_rather_than_zero(tmp_path, monkeypatch):
    """None and 0 mean different things here, and the caller refuses on 0."""

    class Boom:
        SessionOptions = type("Options", (), {"enable_profiling": False})

        @staticmethod
        def InferenceSession(*a, **k):  # noqa: N802
            raise RuntimeError("no such provider")

    monkeypatch.setitem(__import__("sys").modules, "onnxruntime", Boom)
    assert ort_backend.node_assignment("m.onnx", ["QNNExecutionProvider"]) is None


def test_the_probe_runs_before_the_measurement_session_exists():
    """Two concurrent DirectML sessions on one model segfault the process —
    exit 139, no traceback, reproduced on the reference machine. The probe
    opens a session of its own, so its position in `run()` is the whole fix and
    cannot be defended with try/except."""
    import inspect

    source = inspect.getsource(ort_backend.run)
    assert source.index("node_assignment(") < source.index("InferenceSession("), (
        "the assignment probe opens a second session while the measurement "
        "session is alive, which crashes the process on DirectML"
    )


# --- each backend delegates where it should ---------------------------------


def test_windows_ml_is_directml_through_onnx_runtime():
    import inspect

    assert 'device="dml"' in inspect.getsource(windows_ml.run)


def test_qnn_reports_which_half_is_missing(monkeypatch):
    """The SDK and the execution provider fail differently and are fixed
    differently; "qnn not available" covers both and helps with neither."""
    monkeypatch.setattr(qnn, "_has_qnn_provider", lambda: False)
    monkeypatch.setattr(qnn, "sdk_root", lambda: __import__("pathlib").Path("C:/Qualcomm"))
    info = qnn.detect()
    assert info.status is RuntimeStatus.CONFIGURATION_REQUIRED
    assert "onnxruntime-qnn" in (info.detail or "")

    monkeypatch.setattr(qnn, "_has_qnn_provider", lambda: True)
    assert qnn.detect().status is RuntimeStatus.AVAILABLE


def test_rocm_dispatches_on_the_artifact(monkeypatch):
    """An .onnx goes to ONNX Runtime, a GGUF to llama.cpp's HIP build. The
    file decides, because the file is what decides which engine can open it."""
    monkeypatch.setattr(
        rocm,
        "detect",
        lambda: __import__("aihwbench.backends.base", fromlist=["x"]).BackendInfo(
            "rocm", RuntimeStatus.AVAILABLE, "6.2", "rocm"
        ),
    )
    calls = {}
    monkeypatch.setattr(
        rocm, "run_via_onnxruntime", lambda *a, **k: calls.setdefault("ort", k) or {"runtime": {}}
    )
    monkeypatch.setattr(
        rocm, "run_via_llama_cpp", lambda *a, **k: calls.setdefault("llama", k) or {"runtime": {}}
    )

    rocm.run(BenchmarkConfig(model="m", extra={"model_path": "x.onnx"}), {})
    assert "ort" in calls and calls["ort"]["device"] == "rocm"

    calls.clear()
    rocm.run(BenchmarkConfig(model="m", extra={"model_path": "x.gguf"}), {})
    assert "llama" in calls and calls["llama"]["device_prefix"] == "ROCm"


def test_hailo_explains_what_a_hef_is():
    """It is the only backend here that cannot take a model anyone downloads,
    and failing inside the driver would not say so."""
    with pytest.raises(BackendError) as err:
        hailo.hef_path(BenchmarkConfig(model=""))
    assert ".hef" in str(err.value) and "compil" in str(err.value).lower()

    with pytest.raises(BackendError) as err:
        hailo.hef_path(BenchmarkConfig(model="model.onnx"))
    assert "not a .hef" in str(err.value)


def test_exllamav2_keeps_fractional_bits_out_of_ggufs_vocabulary(tmp_path):
    """EXL2 supports 4.65 bits per weight, which has no GGUF equivalent.
    Calling it "q4" would make two incomparable runs look comparable to a
    classifier that only sees quantization strings."""
    import json

    (tmp_path / "config.json").write_text(
        json.dumps({"quantization_config": {"bits": 4.65}}), encoding="utf-8"
    )
    assert exllamav2.bits_per_weight(tmp_path) == 4.65

    (tmp_path / "config.json").write_text(json.dumps({}), encoding="utf-8")
    assert exllamav2.bits_per_weight(tmp_path) is None


def test_mlx_separates_wrong_machine_from_missing_package():
    """Only one of the two is fixable in a minute."""
    info = mlx.detect()
    # This project's machine is not a Mac, so the hardware answer is the right
    # one -- and it must not be reported as a missing package.
    assert info.status is RuntimeStatus.HARDWARE_REQUIRED
    assert "Apple Silicon" in (info.detail or "")


def test_webgpu_still_refuses_the_browser_but_measures_the_native_path():
    """The browser refusal is a reasoned decision, not an unfinished one: a
    result with null power, VRAM and temperature reads to the classifier as
    agreeing with a native result's nulls."""
    import inspect

    source = inspect.getsource(webgpu.run)
    assert "run_via_llama_cpp" in source
    assert "UNMEASURABLE_IN_BROWSER" in source


def test_lemonade_speaks_the_protocol_the_project_already_measures():
    """Its endpoints sit under /api/v1 rather than /v1, which is the only
    thing that made it look like a different problem."""
    assert lemonade.SERVER.host.endswith("/api")
    assert "llm" in lemonade.METADATA.capabilities
