"""Recommendation engine (#21).

Suggests a suitable model size, runtime, device, and context length for
the current hardware. Every recommendation carries its evidence and
uncertainty: it is derived from measured results when they exist, from
the fit estimator's labeled estimates otherwise, and says which.
"""

from __future__ import annotations

from typing import Any

from .fit import estimate_model_fit

__all__ = ["recommend_configuration"]


def recommend_configuration(
    system: dict[str, Any],
    measured_results: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Recommend a configuration for the detected hardware.

    ``measured_results`` are prior result documents from this machine;
    when present, the best measured throughput anchors the runtime/device
    recommendation (evidence tier: "measured"). Otherwise the model-size
    suggestion comes from the fit estimator (tier: "estimated").
    """
    vram_mb = system.get("gpu_vram_mb")
    ram_gb = system.get("ram_gb")
    evidence_tier = "estimated"
    reasons: list[str] = []

    # Model size ceiling: prefer measured VRAM; fall back to RAM with a
    # conservative share for a desktop OS.
    budget_gb: float | None = None
    if isinstance(vram_mb, (int, float)) and vram_mb > 0:
        budget_gb = vram_mb / 1000.0 * 0.9
        reasons.append(
            f"GPU VRAM {vram_mb:.0f} MB -> ~{budget_gb:.1f} GB usable weights budget (90%)"
        )
    elif isinstance(ram_gb, (int, float)) and ram_gb > 0:
        budget_gb = ram_gb * 0.5
        reasons.append(f"no discrete GPU VRAM data; using 50% of {ram_gb:.0f} GB RAM")

    # Anchor on best measured result if available.
    best_runtime: str | None = None
    best_device: str | None = None
    best_tps: float | None = None
    for r in measured_results or []:
        metrics = r.get("metrics", {})
        tps = metrics.get("generation_tokens_per_second")
        if tps is not None and (best_tps is None or tps > best_tps):
            best_tps = tps
            best_runtime = (r.get("runtime") or {}).get("name")
            best_device = (r.get("runtime") or {}).get("device")

    if best_runtime:
        evidence_tier = "measured"
        reasons.append(f"best measured throughput {best_tps:.1f} tok/s on runtime={best_runtime}")

    # Parameter ceiling from bits/weight range: q4 (~4.85 b/w incl overhead)
    # is the common local default; state the assumption.
    max_params_b: float | None = None
    if budget_gb is not None:
        max_params_b = round(budget_gb * 8.0 / 4.85, 1)
        reasons.append(
            f"~{max_params_b}B parameters at Q4_K_M-class density "
            "(4.85 bits/weight incl. overhead) — an estimate"
        )

    context_length = 4096
    if budget_gb is not None and budget_gb < 6.0:
        context_length = 2048
        reasons.append("small memory budget: conservative 2048-token context suggested")

    return {
        "evidence_tier": evidence_tier,
        "recommended_model_parameters_b": max_params_b,
        "recommended_runtime": best_runtime,
        "recommended_device": best_device or ("gpu" if vram_mb else "cpu"),
        "recommended_context_length": context_length,
        "reasons": reasons,
        "uncertainty": (
            "model-size figure is an estimate from memory budget and assumed "
            "quantization density; run 'aihwbench benchmark' to replace it "
            "with measured evidence"
            if evidence_tier == "estimated"
            else "runtime/device anchored on this machine's own measurements"
        ),
        "_fit_example": estimate_model_fit(
            f"{max_params_b or 0}B",
            "q4_k_m",
            available_vram_mb=vram_mb,
            available_ram_mb=ram_gb * 1000.0 if ram_gb else None,
        ),
    }
