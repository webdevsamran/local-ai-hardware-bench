"""Tests for the normalized hardware database."""

from __future__ import annotations

from aihwbench.hardware_db import HardwareClass, classify, normalize_cpu, normalize_gpu


def test_nvidia_laptop_gpu_classification():
    ident = normalize_gpu("NVIDIA GeForce RTX 3080 Ti Laptop GPU")
    assert ident.vendor == "NVIDIA"
    assert ident.device_class == HardwareClass.GPU
    assert ident.family == "rtx-30"
    assert ident.architecture == "ampere"
    assert "mobile" in ident.capabilities


def test_desktop_flagship_capability():
    ident = normalize_gpu("NVIDIA GeForce RTX 4090")
    assert "large-vram" in ident.capabilities
    assert ident.architecture == "ada-lovelace"


def test_amd_rdna_classification():
    ident = normalize_gpu("AMD Radeon RX 7900 XTX")
    assert ident.vendor == "AMD"
    assert ident.family == "radeon-rx"


def test_intel_arc_classification():
    ident = normalize_gpu("Intel(R) Arc(TM) A770 Graphics")
    assert ident.vendor == "Intel"
    assert ident.family == "arc"


def test_npu_detection():
    ident = normalize_gpu("Intel(R) AI Boost")
    assert ident.device_class == HardwareClass.NPU
    assert "npu-inference" in ident.capabilities


def test_cpu_classification():
    ident = normalize_cpu("12th Gen Intel(R) Core(TM) i9-12900H")
    assert ident.vendor == "Intel"
    assert ident.device_class == HardwareClass.CPU
    assert ident.family == "core"
    assert "hybrid-architecture" in ident.capabilities


def test_unknown_device_is_honest():
    ident = classify("Some Unheard-of Accelerator 9000")
    # Vendor may match nothing; class stays unknown rather than guessed.
    assert ident.raw_name == "Some Unheard-of Accelerator 9000"


def test_empty_name_handled():
    ident = classify("")
    assert ident.device_class == HardwareClass.UNKNOWN


def test_no_pii_in_identity():
    ident = normalize_gpu("NVIDIA GeForce RTX 3080 Ti Laptop GPU")
    data = ident.as_dict()
    for key in ("serial", "uuid", "mac", "path"):
        assert key not in data
