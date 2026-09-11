"""Mixture-of-experts: why a MoE model's VRAM question has two answers.

A dense model has one memory number. A MoE model has two, and conflating them
is how people come to believe a 30B-A3B model needs the memory of a 3B one.

**Resident size** is every expert, because the router may pick any of them and
the choice changes per token. That is what has to fit.

**Active size** is the `expert_used_count` experts a single token actually
runs through. That is what bounds arithmetic per token, and therefore roughly
what sets speed.

The names sell the second number -- "A3B" means three billion *active*
parameters -- and a buyer who reads it as a memory requirement will size a
card that cannot hold the model. The opposite error is just as common:
assuming a MoE model is as slow as its total size suggests, when its
per-token work is much smaller.

This is also why expert offload behaves unlike layer offload. Offloading
transformer layers moves a fixed share of the work across PCIe every token.
Offloading experts moves a *variable* share: how much traffic depends on which
experts the router picks, so the cost is a distribution rather than a constant,
and a single average hides how bad the tail is.

Everything here is computed from the model's own GGUF header. Nothing is
inferred from a name: "A3B" in a filename is marketing, and
`expert_used_count` is the header stating a fact.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "read_moe_geometry",
    "expert_memory_split",
    "offload_traffic_per_token",
]


def read_moe_geometry(path: str) -> dict[str, Any]:
    """Expert configuration from a GGUF header.

    `is_moe` is False for a dense model and None when the header could not be
    read at all -- "this model has no experts" and "nobody looked" are
    different answers, and the second must not be reported as the first.
    """
    from ..gguf import read_gguf_header

    metadata = read_gguf_header(path)
    architecture = metadata.get("general.architecture")
    if not isinstance(architecture, str):
        return {
            "architecture": None,
            "is_moe": None,
            "expert_count": None,
            "expert_used_count": None,
            "reason": "no readable GGUF header, so nothing is known about experts",
        }

    def _int(key: str) -> int | None:
        value = metadata.get(f"{architecture}.{key}")
        return int(value) if isinstance(value, int) else None

    expert_count = _int("expert_count")
    return {
        "architecture": architecture,
        "is_moe": bool(expert_count and expert_count > 1),
        "expert_count": expert_count,
        "expert_used_count": _int("expert_used_count"),
        "expert_feed_forward_length": _int("expert_feed_forward_length"),
        "shared_expert_feed_forward_length": _int("expert_shared_feed_forward_length"),
        "block_count": _int("block_count"),
        "embedding_length": _int("embedding_length"),
        "feed_forward_length": _int("feed_forward_length"),
        "reason": None,
    }


def expert_memory_split(
    geometry: dict[str, Any],
    bits_per_weight: float = 4.5,
) -> dict[str, Any]:
    """How much of the model is experts, and how much of that runs per token.

    Returns None fields rather than guesses when the header did not state the
    geometry: a MoE memory estimate assembled from defaults is exactly the
    confident wrong number this is meant to replace.

    `bits_per_weight` defaults to q4_K_M's real cost rather than a nominal 4,
    for the reason the KV-cache module spells out: block formats carry scales,
    and a 12% understatement is how a capacity estimate comes to promise a fit
    that does not happen.
    """
    if not geometry.get("is_moe"):
        return {
            "is_moe": geometry.get("is_moe"),
            "resident_expert_bytes": None,
            "active_expert_bytes": None,
            "reason": (
                "not a mixture-of-experts model"
                if geometry.get("is_moe") is False
                else geometry.get("reason") or "expert geometry unknown"
            ),
        }

    layers = geometry.get("block_count")
    experts = geometry.get("expert_count")
    used = geometry.get("expert_used_count")
    width = geometry.get("embedding_length")
    ffn = geometry.get("expert_feed_forward_length") or geometry.get("feed_forward_length")
    if not all(isinstance(v, int) and v > 0 for v in (layers, experts, used, width, ffn)):
        return {
            "is_moe": True,
            "resident_expert_bytes": None,
            "active_expert_bytes": None,
            "reason": (
                "the header does not state the full expert geometry, and a "
                "memory figure built from defaults would be quoted as measured"
            ),
        }

    # Three matrices per expert in a gated feed-forward block (gate, up, down).
    per_expert = 3 * int(width) * int(ffn)
    bytes_per_weight = bits_per_weight / 8.0
    resident = int(layers) * int(experts) * per_expert * bytes_per_weight
    active = int(layers) * int(used) * per_expert * bytes_per_weight

    return {
        "is_moe": True,
        "expert_count": experts,
        "expert_used_count": used,
        "bits_per_weight": bits_per_weight,
        # What must fit on the card: the router may pick any expert, and the
        # choice changes per token, so none of them can be left out.
        "resident_expert_bytes": round(resident),
        # What one token runs through: the figure model names advertise.
        "active_expert_bytes": round(active),
        "active_fraction": round(int(used) / int(experts), 4),
        "reason": None,
        "caveat": (
            f"{used} of {experts} experts run per token, so the active figure is "
            f"{int(used) / int(experts):.1%} of the resident one. The resident "
            "figure is the memory requirement; the active figure is roughly "
            "what sets speed. A model named for its active size will not fit a "
            "card sized from that name."
        ),
    }


def offload_traffic_per_token(
    split: dict[str, Any],
    experts_kept_resident: int,
) -> dict[str, Any]:
    """Bytes crossing PCIe per token when only some experts stay in VRAM.

    Unlike layer offload, the answer is a distribution rather than a number:
    traffic depends on which experts the router picks, which changes per token.
    Reported as best and worst case rather than an average, because the tail is
    what a user feels and an average hides it.

    The expected case assumes the router picks uniformly, which real routers do
    not -- they are usually skewed, and a skewed router with the popular
    experts resident does far better than this says. It is stated as an
    assumption rather than presented as a measurement.
    """
    experts = split.get("expert_count")
    used = split.get("expert_used_count")
    resident_bytes = split.get("resident_expert_bytes")
    if not all(isinstance(v, int) and v > 0 for v in (experts, used)) or not resident_bytes:
        return {"unresolved": "expert geometry unknown, so traffic cannot be computed"}

    kept = max(0, min(int(experts_kept_resident), int(experts)))
    per_expert = resident_bytes / int(experts)
    offloaded = int(experts) - kept

    worst = min(int(used), offloaded) * per_expert
    best = max(0, int(used) - kept) * per_expert
    expected = int(used) * (offloaded / int(experts)) * per_expert

    return {
        "experts_kept_resident": kept,
        "experts_offloaded": offloaded,
        "bytes_per_token_best_case": round(best),
        "bytes_per_token_expected_uniform": round(expected),
        "bytes_per_token_worst_case": round(worst),
        "assumption": (
            "the expected case assumes the router picks experts uniformly. Real "
            "routers are skewed, so keeping the most-used experts resident does "
            "better than this figure -- which is a reason to measure the router, "
            "not to trust the average."
        ),
        "unresolved": None,
    }
