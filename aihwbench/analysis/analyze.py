"""Bottleneck analyzer (#22).

Identifies probable compute, VRAM, RAM, thermal, or I/O bottlenecks from
measured telemetry using explicit, auditable rules. Each finding records
the rule that fired and the evidence values — no opaque scoring.
"""

from __future__ import annotations

from typing import Any

__all__ = ["analyze_bottlenecks"]


def analyze_bottlenecks(
    metrics: dict[str, Any], system: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    """Return findings sorted by confidence tier (high first).

    Rules fire only on measured values; missing telemetry produces no
    finding rather than a guess.
    """
    system = system or {}
    findings: list[dict[str, Any]] = []

    def add(kind: str, rule: str, evidence: dict[str, Any]) -> None:
        findings.append({"bottleneck": kind, "rule": rule, "evidence": evidence})

    gpu_util = metrics.get("avg_gpu_util_percent")
    cpu_util = metrics.get("avg_cpu_util_percent")
    vram = metrics.get("peak_vram_mb")
    ram = metrics.get("peak_ram_mb")
    temp = metrics.get("max_temperature_c")
    ttft = metrics.get("ttft_ms")
    prompt_tps = metrics.get("prompt_tokens_per_second")

    if gpu_util is not None and gpu_util >= 90.0:
        add("gpu_compute", "avg_gpu_util_percent >= 90", {"avg_gpu_util_percent": gpu_util})
    if gpu_util is not None and cpu_util is not None and gpu_util < 60.0 and cpu_util >= 85.0:
        add(
            "cpu",
            "gpu_util < 60 and cpu_util >= 85 (GPU starved by host)",
            {"avg_gpu_util_percent": gpu_util, "avg_cpu_util_percent": cpu_util},
        )
    if vram is not None:
        total_vram = system.get("gpu_vram_mb")
        if isinstance(total_vram, (int, float)) and total_vram > 0 and vram >= 0.95 * total_vram:
            add(
                "vram_capacity",
                "peak_vram_mb >= 95% of gpu_vram_mb",
                {"peak_vram_mb": vram, "gpu_vram_mb": total_vram},
            )
    if ram is not None:
        total_ram_gb = system.get("ram_gb")
        if isinstance(total_ram_gb, (int, float)) and total_ram_gb > 0:
            total_ram_mb = total_ram_gb * 1000.0
            if ram >= 0.9 * total_ram_mb:
                add(
                    "system_memory",
                    "peak_ram_mb >= 90% of installed RAM",
                    {"peak_ram_mb": ram, "ram_mb_total": total_ram_mb},
                )
    if temp is not None and temp >= 85.0:
        add("thermal", "max_temperature_c >= 85", {"max_temperature_c": temp})
    if ttft is not None and prompt_tps is not None and prompt_tps < 50.0 and ttft > 2000.0:
        add(
            "prefill_io_or_memory_bandwidth",
            "prompt_tokens_per_second < 50 with ttft_ms > 2000 "
            "(slow prefill: bandwidth or storage-bound)",
            {"prompt_tokens_per_second": prompt_tps, "ttft_ms": ttft},
        )

    order = {
        "gpu_compute": 0,
        "vram_capacity": 1,
        "thermal": 2,
        "cpu": 3,
        "system_memory": 4,
        "prefill_io_or_memory_bandwidth": 5,
    }
    findings.sort(key=lambda f: order.get(f["bottleneck"], 99))
    return findings
