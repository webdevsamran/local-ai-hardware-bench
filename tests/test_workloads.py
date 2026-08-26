"""Tests for the workload engine and registry."""

from __future__ import annotations

import pytest

from aihwbench.workloads import (
    ISL_OSL_PROFILES,
    TrafficMixItem,
    TurnSpec,
    Workload,
    get_workload,
    list_workloads,
)
from aihwbench.workloads.builtin import (
    build_multi_turn_prompts,
    sample_traffic_mix,
    synthesize_prompt,
)


def test_builtin_workloads_registered():
    ids = list_workloads()
    for expected in (
        "default_chat",
        "prefill_only",
        "decode_only",
        "multi_turn_8",
        "mixed_traffic_realistic",
    ):
        assert expected in ids


def test_isl_osl_profiles_exist():
    for profile in ("chat_short", "long_prompt", "long_generation", "long_context"):
        w = ISL_OSL_PROFILES[profile]
        assert w.isl_tokens is not None and w.osl_tokens is not None


def test_workload_requires_valid_kind():
    with pytest.raises(ValueError):
        Workload(id="bad", kind="not-a-kind")


def test_workload_id_no_whitespace():
    with pytest.raises(ValueError):
        Workload(id="has space", kind="generation")


def test_multi_turn_workload_requires_turns():
    with pytest.raises(ValueError):
        Workload(id="empty_turns", kind="multi_turn")


def test_traffic_mix_weights_must_sum_to_one():
    with pytest.raises(ValueError):
        Workload(
            id="bad_mix",
            kind="combined",
            traffic_mix=(TrafficMixItem(weight=0.5, isl_tokens=1, osl_tokens=1),),
        )


def test_prompt_synthesis_is_deterministic():
    a = synthesize_prompt(256, seed=7)
    b = synthesize_prompt(256, seed=7)
    c = synthesize_prompt(256, seed=8)
    assert a == b
    assert a != c
    # Approximate length shaping (~4 chars/token), never an exact claim.
    assert len(a) >= 256 * 3


def test_traffic_mix_sampling_is_deterministic_and_weighted():
    mix = get_workload("mixed_traffic_realistic").traffic_mix
    first = [sample_traffic_mix(mix, i) for i in range(200)]
    again = [sample_traffic_mix(mix, i) for i in range(200)]
    assert first == again
    short_short = sum(1 for isl, osl in first if isl == 256 and osl == 256)
    # 60% weight over 200 draws; allow generous statistical slack.
    assert 80 <= short_short <= 160


def test_multi_turn_prompts_grow_in_context():
    workload = get_workload("multi_turn_8")
    prompts = build_multi_turn_prompts(workload.turns)
    assert len(prompts) == 8
    lengths = [len(p) for p in prompts]
    assert all(b > a for a, b in zip(lengths, lengths[1:], strict=False)), (
        "context must grow per turn"
    )


def test_workload_as_dict_round_trip():
    w = get_workload("multi_turn_8")
    data = w.as_dict()
    restored = Workload(
        id=data["id"],
        kind=data["kind"],
        version=data["version"],
        description=data["description"],
        turns=tuple(TurnSpec(**t) for t in data["turns"]),
    )
    assert restored.id == w.id
    assert len(restored.turns) == len(w.turns)


def test_with_overrides_returns_copy():
    base = get_workload("chat_short")
    variant = base.with_overrides(osl_tokens=999)
    assert variant.osl_tokens == 999
    assert base.osl_tokens == 128  # original untouched
