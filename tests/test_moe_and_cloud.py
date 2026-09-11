"""A MoE model's VRAM question has two answers, and cloud specs are not prices.

Both modules exist to stop a plausible number being read as the wrong one.

A model named "30B-A3B" advertises its *active* parameter count. Read as a
memory requirement it is off by a factor of sixteen: on the real Qwen3-30B-A3B
geometry, 8 of 128 experts run per token, so the active figure is 6.2% of what
has to be resident. A buyer sizing a card from the name buys the wrong card.

Cloud profiles carry hardware and not prices, because an instance's GPU is a
stable fact and its price is not.
"""

from __future__ import annotations

import re

import pytest

from aihwbench.analysis.moe import (
    expert_memory_split,
    offload_traffic_per_token,
    read_moe_geometry,
)
from aihwbench.cloud import CLOUD_PROFILES, compare_against_profile, get_profile, list_profiles

#: Qwen3-30B-A3B, as its GGUF header states it.
QWEN3_MOE = {
    "architecture": "qwen3moe",
    "is_moe": True,
    "expert_count": 128,
    "expert_used_count": 8,
    "block_count": 48,
    "embedding_length": 2048,
    "expert_feed_forward_length": 768,
}


# --- mixture of experts -----------------------------------------------------


def test_resident_and_active_are_different_numbers():
    """The distinction the model's own name obscures."""
    split = expert_memory_split(QWEN3_MOE)
    assert split["resident_expert_bytes"] > split["active_expert_bytes"]
    assert split["active_fraction"] == pytest.approx(8 / 128, rel=1e-3)
    assert split["resident_expert_bytes"] / split["active_expert_bytes"] == pytest.approx(16.0)


def test_the_caveat_names_which_figure_is_the_memory_requirement():
    split = expert_memory_split(QWEN3_MOE)
    assert "resident figure is the memory requirement" in split["caveat"]


def test_a_dense_model_is_not_described_as_a_mixture():
    split = expert_memory_split({"is_moe": False})
    assert split["resident_expert_bytes"] is None
    assert "not a mixture-of-experts" in split["reason"]


def test_an_unreadable_header_is_unknown_rather_than_dense():
    """ "No experts" and "nobody looked" are different answers."""
    geometry = read_moe_geometry("no-such-file.gguf")
    assert geometry["is_moe"] is None
    assert "nothing is known" in geometry["reason"]
    assert expert_memory_split(geometry)["resident_expert_bytes"] is None


def test_a_partial_geometry_yields_no_figure_rather_than_a_default():
    """A memory estimate built from assumed dimensions would be quoted as
    measured, which is the confident wrong number this replaces."""
    split = expert_memory_split({**QWEN3_MOE, "embedding_length": None})
    assert split["resident_expert_bytes"] is None
    assert "would be quoted as measured" in split["reason"]


def test_quantized_weights_cost_more_than_their_nominal_bit_width():
    """4.5 bits, not 4: block formats carry scales."""
    split = expert_memory_split(QWEN3_MOE)
    assert split["bits_per_weight"] == 4.5


def test_offload_traffic_is_a_range_because_the_router_chooses():
    """Unlike layer offload, the per-token cost is not a constant.

    Reporting only an average hides the tail, and the tail is what a user
    feels.
    """
    split = expert_memory_split(QWEN3_MOE)
    traffic = offload_traffic_per_token(split, experts_kept_resident=96)
    assert traffic["bytes_per_token_best_case"] == 0
    assert traffic["bytes_per_token_worst_case"] > traffic["bytes_per_token_expected_uniform"] > 0
    assert "skewed" in traffic["assumption"]


def test_keeping_every_expert_resident_costs_no_traffic():
    split = expert_memory_split(QWEN3_MOE)
    traffic = offload_traffic_per_token(split, experts_kept_resident=128)
    assert traffic["bytes_per_token_worst_case"] == 0


def test_keeping_none_resident_moves_every_active_expert_each_token():
    split = expert_memory_split(QWEN3_MOE)
    traffic = offload_traffic_per_token(split, experts_kept_resident=0)
    assert traffic["bytes_per_token_best_case"] == traffic["bytes_per_token_worst_case"]
    assert traffic["bytes_per_token_worst_case"] == pytest.approx(
        split["active_expert_bytes"], rel=1e-6
    )


def test_asking_to_keep_more_experts_than_exist_is_clamped():
    split = expert_memory_split(QWEN3_MOE)
    assert offload_traffic_per_token(split, 9999)["experts_kept_resident"] == 128


# --- cloud profiles ---------------------------------------------------------


@pytest.mark.parametrize("key", sorted(CLOUD_PROFILES))
def test_every_profile_cites_where_its_specs_were_read(key):
    """An uncited spec is an assertion; one with a URL and a date is checkable.

    Same rule the licence manifest follows, for the same reason: these go
    stale, and a reader needs to know how stale.
    """
    profile = CLOUD_PROFILES[key]
    assert profile["source"].startswith("https://")
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", profile["specs_read_on"])


@pytest.mark.parametrize("key", sorted(CLOUD_PROFILES))
def test_no_profile_carries_a_price(key):
    """Pricing varies by region, commitment and the spot market.

    A bundled price would go stale quietly and keep producing confident wrong
    answers, which is why `analysis.cost` already requires the caller's figure.
    """
    profile = CLOUD_PROFILES[key]
    assert not [k for k in profile if "usd" in k.lower() or "price" in k.lower()]


def test_a_comparison_without_a_rate_still_says_what_you_would_be_renting():
    """Knowing what you would be renting is useful before knowing its cost."""
    report = compare_against_profile("aws-g5-xlarge", None)
    assert report["profile"]["gpu"] == "NVIDIA A10G"
    assert report["profile"]["gpu_vram_mb"] == 24576
    assert "annual_usd_if_always_on" not in report
    assert "does not carry a price table" in report["unresolved"]


def test_a_rate_gives_an_annual_figure():
    report = compare_against_profile("aws-g5-xlarge", 1.006)
    assert report["annual_usd_if_always_on"] == pytest.approx(1.006 * 24 * 365, rel=1e-6)
    assert report["unresolved"] is None


def test_it_never_claims_a_throughput_it_has_not_measured():
    """A measured local number beside an assumed remote one is the assumption,
    dressed up as a comparison."""
    report = compare_against_profile("aws-g5-xlarge", 1.0)
    assert report["cloud_throughput"] is None
    assert "has not measured one" in report["note"]


def test_it_compares_vram_against_the_local_card():
    report = compare_against_profile(
        "aws-g5-xlarge", 1.0, {"system": {"gpu_vram_mb": 16384, "gpu": "RTX 3080 Ti"}}
    )
    assert report["vram_ratio_local_over_cloud"] == pytest.approx(16384 / 24576, rel=1e-3)


def test_an_unknown_profile_names_the_ones_that_exist():
    with pytest.raises(KeyError, match="known:"):
        get_profile("aws-nonexistent")
    assert list_profiles()
