"""Normalized hardware identifiers, aliases, and capabilities.

Maps raw detected device names (e.g. "NVIDIA GeForce RTX 3080 Ti Laptop
GPU") to stable, comparable classes: vendor, device family, class
(CPU/GPU/NPU), microarchitecture where known, and capability flags.

This is a *classification* layer only — it never invents hardware that was
not detected, never stores serial numbers or PII, and unknown devices are
reported as ``vendor=None``/``class="unknown"`` rather than guessed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

__all__ = ["HardwareClass", "HardwareIdentity", "classify", "normalize_cpu", "normalize_gpu"]


class HardwareClass:
    CPU = "cpu"
    GPU = "gpu"
    NPU = "npu"
    ACCELERATOR = "accelerator"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class HardwareIdentity:
    """Stable identity for one detected device."""

    raw_name: str
    vendor: str | None = None
    device_class: str = HardwareClass.UNKNOWN
    family: str | None = None  # e.g. "rtx-40", "core-ultra", "ryzen-ai"
    architecture: str | None = None  # e.g. "ada-lovelace", "x86-64-v3"
    capabilities: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict[str, object]:
        return {
            "raw_name": self.raw_name,
            "vendor": self.vendor,
            "device_class": self.device_class,
            "family": self.family,
            "architecture": self.architecture,
            "capabilities": list(self.capabilities),
        }


# Vendor patterns applied in order; first match wins.
_VENDOR_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"nvidia|geforce|quadro|tesla", "NVIDIA"),
    (r"amd|radeon|ryzen|athlon|instinct", "AMD"),
    (r"intel|core\(tm\)|xeon|arc|iris|uhd graphics", "Intel"),
    (r"qualcomm|snapdragon", "Qualcomm"),
    (r"apple|m1|m2|m3|m4", "Apple"),
    (r"hailo", "Hailo"),
    (r"arm\b|cortex|neoverse", "ARM"),
)

# GPU family patterns -> (family, architecture)
_GPU_FAMILIES: tuple[tuple[str, str, str], ...] = (
    (r"rtx\s*50\d\d", "rtx-50", "blackwell"),
    (r"rtx\s*40\d\d", "rtx-40", "ada-lovelace"),
    (r"rtx\s*30\d\d", "rtx-30", "ampere"),
    (r"rtx\s*20\d\d", "rtx-20", "turing"),
    (r"gtx\s*16\d\d", "gtx-16", "turing"),
    (r"rx\s*[678]\d{3}", "radeon-rx", "rdna"),
    (r"rx\s*9\d{3}", "radeon-rx", "rdna4"),
    (r"arc.*a\d{3}", "arc", "alchemist"),
    (r"iris\s*xe", "iris-xe", "xelp"),
    (r"apple\s*m[1-4]", "apple-silicon", "unified"),
)

# Capability flags derivable from the name alone.
_CAPABILITY_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\b4090\b|\b3090\b|\b5090\b|h100|mi300", "large-vram"),
    (r"laptop|mobile|max-q", "mobile"),
    (r"integrated|uhd graphics|iris", "integrated"),
    (r"ai boost|ryzen ai|hexagon|neural engine|xdna", "npu-inference"),
)


def _match_vendor(name: str) -> str | None:
    lowered = name.lower()
    for pattern, vendor in _VENDOR_PATTERNS:
        if re.search(pattern, lowered):
            return vendor
    return None


def normalize_gpu(raw_name: str) -> HardwareIdentity:
    """Classify a GPU/NPU device name."""
    vendor = _match_vendor(raw_name)
    family = arch = None
    for pattern, fam, architecture in _GPU_FAMILIES:
        if re.search(pattern, raw_name.lower()):
            family, arch = fam, architecture
            break
    caps = tuple(
        flag for pattern, flag in _CAPABILITY_PATTERNS if re.search(pattern, raw_name.lower())
    )
    device_class = (
        HardwareClass.NPU if any(c == "npu-inference" for c in caps) else HardwareClass.GPU
    )
    return HardwareIdentity(
        raw_name=raw_name,
        vendor=vendor,
        device_class=device_class,
        family=family,
        architecture=arch,
        capabilities=caps,
    )


def normalize_cpu(raw_name: str) -> HardwareIdentity:
    """Classify a CPU name."""
    vendor = _match_vendor(raw_name)
    family = None
    lowered = raw_name.lower()
    for pattern, fam in (
        (r"core.*i[3579]", "core"),
        (r"core\s*ultra", "core-ultra"),
        (r"ryzen", "ryzen"),
        (r"xeon", "xeon"),
        (r"threadripper", "threadripper"),
        (r"cortex|neoverse", "arm-cortex"),
        (r"snapdragon", "snapdragon"),
    ):
        if re.search(pattern, lowered):
            family = fam
            break
    return HardwareIdentity(
        raw_name=raw_name,
        vendor=vendor,
        device_class=HardwareClass.CPU,
        family=family,
        capabilities=("hybrid-architecture",)
        if re.search(r"12900|13900|14900|ultra", lowered)
        else (),
    )


def classify(raw_name: str, device_class_hint: str | None = None) -> HardwareIdentity:
    """Classify any device name; hint may be 'cpu', 'gpu', or 'npu'."""
    if not raw_name or not isinstance(raw_name, str):
        return HardwareIdentity(raw_name=str(raw_name))
    if device_class_hint == HardwareClass.CPU:
        return normalize_cpu(raw_name)
    if device_class_hint in (HardwareClass.GPU, HardwareClass.NPU):
        return normalize_gpu(raw_name)
    # Heuristic: CPUs usually come from cpu fields; try both and prefer
    # whichever produces a stronger signal.
    gpu_guess = normalize_gpu(raw_name)
    if gpu_guess.vendor is not None and gpu_guess.family is not None:
        return gpu_guess
    cpu_guess = normalize_cpu(raw_name)
    if cpu_guess.family is not None:
        return cpu_guess
    return gpu_guess if gpu_guess.vendor else cpu_guess
