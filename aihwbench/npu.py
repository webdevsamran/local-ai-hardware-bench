"""NPU telemetry hooks (#18).

NPUs (Intel AI Boost, AMD XDNA, Qualcomm Hexagon) currently expose no
portable, dependency-free utilization/power counters that this project
can read. The hooks below provide the structured contract for NPU
telemetry: fields always exist, values stay ``None`` until a real
driver counter is wired per platform, and the source is declared
honestly. Nothing is fabricated.
"""

from __future__ import annotations

from typing import Any

__all__ = ["NPU_FIELDS", "npu_telemetry", "enrich_with_npu"]

NPU_FIELDS = ("npu_util_percent", "npu_power_watts", "npu_memory_used_mb")


def npu_telemetry(system: dict[str, Any] | None = None) -> dict[str, Any]:
    """Honest NPU telemetry block.

    ``npu_device`` mirrors the detected NPU string (``system_info``
    already sanitizes it); the metric fields remain ``None`` — NPUs are
    enumerated, never estimated. ``npu_telemetry_source`` states why the
    values are absent so downstream consumers never mistake "not
    measured" for "measured zero".
    """
    device = (system or {}).get("npu") or None
    out: dict[str, Any] = {
        "npu_device": device,
        "npu_telemetry_source": (
            "driver counters not wired for this platform"
            if device
            else "no NPU detected"
        ),
    }
    out.update({field: None for field in NPU_FIELDS})
    return out


def enrich_with_npu(
    summary: dict[str, Any],
    system: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a copy of a telemetry/metrics mapping plus NPU hook fields.

    The input mapping is never mutated; unknown NPU state can never
    overwrite a measured value because all hook fields are ``None``.
    """
    merged = dict(summary)
    merged.update(npu_telemetry(system))
    return merged
