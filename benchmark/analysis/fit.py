"""Model-fit estimator (#20).

Estimates whether a model variant fits in available memory using model
metadata (parameter count, quantization bits) and standard weight-bytes
arithmetic. Output is clearly labeled as an ESTIMATE with recorded
assumptions — never presented as a measured fact. Measured peak memory
from a real run, when present, always takes precedence.
"""

from __future__ import annotations

import re
from typing import Any

__all__ = ["estimate_model_fit", "parse_parameter_count", "BITS_PER_WEIGHT"]

# Bits per weight by quantization label. These are format conventions,
# not measurements; unknown labels are rejected rather than guessed.
BITS_PER_WEIGHT: dict[str, float] = {
    "fp32": 32.0,
    "fp16": 16.0,
    "bf16": 16.0,
    "f16": 16.0,
    "q8_0": 8.5,
    "q8": 8.5,
    "int8": 8.0,
    "q6_k": 6.5625,
    "q5_k_m": 5.67,
    "q5_k_s": 5.54,
    "q5_0": 5.54,
    "q5_1": 6.7,
    "q4_k_m": 4.85,
    "q4_k_s": 4.58,
    "q4_0": 4.55,
    "q4_1": 5.0,
    "q3_k_m": 3.91,
    "q3_k_s": 3.5,
    "q2_k": 3.35,
    "iq4_xs": 4.25,
    "iq3_xxs": 3.06,
    "iq2_xxs": 2.06,
}

_PARAM_RE = re.compile(r"([\d.]+)\s*([bmk])\b", re.IGNORECASE)
_MULTIPLIERS = {"k": 1e3, "m": 1e6, "b": 1e9}


def parse_parameter_count(text: str | None) -> float | None:
    """Parse '7B', '1.5b', '350M' style parameter counts."""
    if not text:
        return None
    match = _PARAM_RE.search(text)
    if not match:
        return None
    value = float(match.group(1))
    unit = match.group(2).lower()
    return value * _MULTIPLIERS[unit]


def estimate_model_fit(
    parameters_text: str | None,
    quantization: str | None,
    available_vram_mb: float | None = None,
    available_ram_mb: float | None = None,
    context_tokens: int = 4096,
    overhead_factor: float = 1.15,
) -> dict[str, Any]:
    """Estimate memory need vs availability.

    ``overhead_factor`` covers KV cache, activations, and runtime overhead
    beyond raw weights; it is an assumption, recorded in the output.
    """
    params = parse_parameter_count(parameters_text)
    if params is None:
        return {
            "estimated_weights_gb": None,
            "estimated_total_gb": None,
            "fits": None,
            "reason": "parameter count unavailable; cannot estimate",
            "assumptions": {},
        }
    bits = BITS_PER_WEIGHT.get((quantization or "").lower())
    if bits is None:
        return {
            "estimated_weights_gb": None,
            "estimated_total_gb": None,
            "fits": None,
            "reason": f"unknown quantization {quantization!r}; refusing to guess bits-per-weight",
            "assumptions": {"known_quantizations": sorted(BITS_PER_WEIGHT)},
        }
    weights_bytes = params * bits / 8.0
    total_bytes = weights_bytes * overhead_factor
    total_gb = total_bytes / 1e9
    assumptions = {
        "bits_per_weight": bits,
        "overhead_factor": overhead_factor,
        "context_tokens": context_tokens,
        "note": (
            "estimate from parameter count x bits/weight x overhead factor; "
            "KV cache scales with context and is approximated by the factor"
        ),
    }
    candidates: list[tuple[str, float]] = []
    if available_vram_mb is not None:
        candidates.append(("vram", available_vram_mb / 1000.0))
    if available_ram_mb is not None:
        candidates.append(("ram", available_ram_mb / 1000.0))
    fits: bool | None = None
    target: str | None = None
    for name, gb in candidates:
        if gb >= total_gb:
            fits = True
            target = name
            break
        fits = False
        target = name
    return {
        "estimated_weights_gb": round(weights_bytes / 1e9, 3),
        "estimated_total_gb": round(total_gb, 3),
        "fits": fits,
        "fit_target": target,
        "reason": (
            f"estimated {total_gb:.2f} GB needed vs "
            + ", ".join(f"{n} {gb:.1f} GB" for n, gb in candidates)
            if candidates
            else "no memory availability supplied"
        ),
        "assumptions": assumptions,
    }
