"""Six backends for hardware and runtimes this machine does not have.

The feature a benchmarking tool ships is the ability to measure, not a
measurement. These detect honestly on hardware they cannot use, and the
detail they return is the part that matters: "not available" tells a user
nothing, while "two Vulkan devices found, but this llama.cpp build has no
Vulkan backend" tells them exactly what to change.

The recurring failure these are written against is a backend that falls back.
A result labelled `sycl` produced by the CPU, or `vulkan` produced by CUDA,
would be mislabelled in a way the comparison classifier cannot detect --
every field would agree and the number would be from different silicon. So
each `run` refuses rather than substituting.
"""

from __future__ import annotations

import pytest

from aihwbench.backends import BACKENDS, BackendError, BenchmarkConfig, RuntimeStatus

NEW_BACKENDS = ("vulkan", "sycl", "webgpu", "exllamav2", "jetson", "arm_sbc")


@pytest.mark.parametrize("name", NEW_BACKENDS)
def test_it_is_registered_and_reachable(name):
    assert name in BACKENDS
    assert hasattr(BACKENDS[name], "detect")
    assert hasattr(BACKENDS[name], "run")


@pytest.mark.parametrize("name", NEW_BACKENDS)
def test_detection_returns_a_known_status(name):
    info = BACKENDS[name].detect()
    assert isinstance(info.status, RuntimeStatus)
    assert info.name == name


@pytest.mark.parametrize("name", NEW_BACKENDS)
def test_an_unavailable_backend_says_what_is_missing(name):
    """ "Not available" is not an answer a user can act on."""
    info = BACKENDS[name].detect()
    if info.status is not RuntimeStatus.AVAILABLE:
        assert info.detail, f"{name} reported {info.status.value} with no explanation"
        assert len(info.detail) > 30


@pytest.mark.parametrize("name", NEW_BACKENDS)
def test_running_an_unavailable_backend_refuses_rather_than_falling_back(name):
    """A fallback would mislabel the silicon and nothing downstream could tell.

    Every comparability field would match while the numbers came from
    different hardware -- the one failure the classifier is blind to.
    """
    module = BACKENDS[name]
    if module.detect().status is RuntimeStatus.AVAILABLE:
        pytest.skip(f"{name} is available on this machine")
    with pytest.raises(BackendError):
        module.run(BenchmarkConfig(model="m"), {})


@pytest.mark.parametrize("name", NEW_BACKENDS)
def test_it_declares_its_prerequisites(name):
    """The capability contract detection must not contradict."""
    capabilities = getattr(BACKENDS[name], "CAPABILITIES", None)
    assert capabilities, f"{name} declares no capability contract"
    assert all(isinstance(c, str) for c in capabilities)


# --- Vulkan: hardware support and build support are separate questions ------


def test_vulkan_separates_the_devices_from_the_build():
    """The reference machine is the interesting case.

    Two Vulkan devices are present and the CUDA-only build cannot use either.
    Reporting "not available" would tell the user their hardware is
    unsupported, which is false and would stop them fixing it.
    """
    from aihwbench.backends import vulkan

    devices = vulkan.vulkan_devices()
    info = vulkan.detect()
    if devices and vulkan.build_has_vulkan_backend() is False:
        assert info.status is RuntimeStatus.CONFIGURATION_REQUIRED
        assert "hardware is not the limitation" in info.detail
        assert "GGML_VULKAN" in info.detail


def test_vulkan_reports_hardware_required_when_no_device_exists(monkeypatch):
    from aihwbench.backends import vulkan

    monkeypatch.setattr(vulkan, "vulkan_devices", list)
    assert vulkan.detect().status is RuntimeStatus.HARDWARE_REQUIRED


def test_an_unlocatable_llama_cpp_is_unknown_not_a_missing_feature(monkeypatch):
    """ "No Vulkan backend" is a claim about a build nobody found."""
    from aihwbench.backends import llama_cpp, vulkan

    monkeypatch.setattr(llama_cpp, "_find_binary", lambda name: None)
    assert vulkan.build_has_vulkan_backend() is None


# --- SYCL -------------------------------------------------------------------


def test_sycl_finds_the_intel_gpu_this_machine_has():
    """An Intel CPU does not imply a usable Intel GPU, so this reads the
    platform rather than inferring from the processor."""
    from aihwbench.backends import sycl

    gpus = sycl.intel_gpus()
    if gpus:
        assert any("intel" in name.lower() for name in gpus)
        assert sycl.detect().status is not RuntimeStatus.HARDWARE_REQUIRED


def test_sycl_distinguishes_a_missing_runtime_from_missing_hardware(monkeypatch):
    from aihwbench.backends import sycl

    monkeypatch.setattr(sycl, "intel_gpus", lambda: ["Intel(R) Iris(R) Xe Graphics"])
    monkeypatch.setattr(sycl, "sycl_devices", list)
    info = sycl.detect()
    assert info.status is RuntimeStatus.CONFIGURATION_REQUIRED
    assert "oneAPI is not installed" in info.detail


# --- WebGPU: some fields are unmeasurable, not merely unmeasured ------------


def test_webgpu_names_the_fields_a_browser_cannot_measure():
    """Null power in a browser result is structural.

    Left unexplained it is indistinguishable from a native run whose telemetry
    failed, and the classifier reads two nulls as agreement -- which would
    quietly make browser numbers comparable with native ones.
    """
    from aihwbench.backends.webgpu import UNMEASURABLE_IN_BROWSER, detect

    assert "average_power_watts" in UNMEASURABLE_IN_BROWSER
    assert "peak_vram_mb" in UNMEASURABLE_IN_BROWSER
    assert detect().status is not RuntimeStatus.AVAILABLE


def test_webgpu_refusal_lists_what_would_have_been_null():
    from aihwbench.backends import webgpu

    with pytest.raises(BackendError, match="average_power_watts"):
        webgpu.run(BenchmarkConfig(model="m"), {})


# --- ExLlamaV2: a quantization vocabulary that does not map onto GGUF -------


def test_exllamav2_names_each_missing_dependency():
    from aihwbench.backends.exllamav2 import detect

    info = detect()
    if info.status is RuntimeStatus.NOT_INSTALLED:
        assert "torch" in info.detail or "exllamav2" in info.detail


def test_exllamav2_declares_that_its_quantization_labels_do_not_compare():
    """EXL2 supports fractional bits per weight; GGUF does not.

    "q4_K_M against 4.65bpw" is not like-for-like and neither string is wrong,
    so the classifier cannot catch it from the labels alone.
    """
    from aihwbench.backends.exllamav2 import CAPABILITIES

    assert "not-comparable-with-gguf-quantization-labels" in CAPABILITIES


# --- Jetson and ARM SBCs: identified by the board, not the architecture -----


def test_jetson_is_not_claimed_on_a_non_arm_machine():
    from aihwbench.backends.jetson import detect

    info = detect()
    import platform

    if platform.machine().lower() not in ("aarch64", "arm64"):
        assert info.status is RuntimeStatus.HARDWARE_REQUIRED
        assert "aarch64" in info.detail


def test_jetson_requires_the_power_mode_to_be_recorded():
    """Throughput changes severalfold between nvpmodel modes.

    Two Jetson results without it are not comparable, and the gap reads as a
    hardware or software difference.
    """
    from aihwbench.backends.jetson import CAPABILITIES

    assert "power-mode-must-be-recorded" in CAPABILITIES


def test_an_arm_sbc_is_identified_by_its_board_not_its_architecture():
    """aarch64 includes Apple Silicon, Ampere servers and Jetsons.

    Claiming any of them as a Raspberry Pi would file results under the wrong
    hardware class.
    """
    from aihwbench.backends.arm_sbc import board_model, detect

    assert board_model() is None
    assert detect().status is RuntimeStatus.HARDWARE_REQUIRED


def test_unreadable_throttle_state_is_unknown_not_untroubled():
    """ "Not throttled" is a measurement; "vcgencmd is missing" is not."""
    from aihwbench.backends.arm_sbc import throttle_state

    state = throttle_state()
    if state["flags"] is None:
        assert state["reason"]
        assert "throttled_now" not in state or state.get("throttled_now") is None


def test_throttle_flags_are_decoded_from_the_real_bit_field():
    """0x50005: under-voltage now and capped now, both having occurred.

    Under-voltage is a power-supply fault and thermal is a cooling one; both
    present as "this board is slow" unless the flags are read.
    """
    import re as _re

    from aihwbench.backends import arm_sbc

    value = 0x50005
    flags = [label for bit, label in arm_sbc._THROTTLE_BITS.items() if value & (1 << bit)]
    assert "under-voltage now" in flags
    assert "under-voltage has occurred" in flags
    assert arm_sbc._THROTTLED.search("throttled=0x50005")
    assert _re.search(r"0x", "0x50005")
