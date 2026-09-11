"""Every non-text modality reports its own unit, and none of them is tok/s.

Forcing a modality into tokens per second is how these benchmarks come to
publish numbers nobody can act on: a real-time factor read as a generation rate
compares different quantities, and the two look alike because both are numbers
that go up when things are good.

Each entry also declares what it *needs*, so a machine that cannot measure a
modality says which piece is missing rather than reporting it unsupported.
"""

from __future__ import annotations

import pytest

from aihwbench.modalities import DEFAULT_EMBED_BATCHES, MODALITIES, modality_inventory


@pytest.mark.parametrize("name", sorted(MODALITIES))
def test_every_modality_states_its_unit_and_it_is_not_tokens_per_second(name):
    spec = MODALITIES[name]
    assert spec["unit"]
    assert "token" not in spec["unit"].lower(), (
        f"{name} reports {spec['unit']!r}; reading that as a generation rate "
        "would compare different quantities"
    )


@pytest.mark.parametrize("name", sorted(MODALITIES))
def test_every_modality_says_why_that_unit(name):
    """A unit without a reason invites someone to 'simplify' it later."""
    assert len(MODALITIES[name]["why"]) > 30


@pytest.mark.parametrize("name", sorted(MODALITIES))
def test_every_modality_says_what_it_needs(name):
    assert MODALITIES[name]["needs"]


@pytest.mark.parametrize("name", sorted(MODALITIES))
def test_every_modality_names_the_axis_that_dominates_it(name):
    """A single figure at one point on the curve is the usual mistake.

    Embedding at batch 1 and embedding at batch 64 differ by more than most
    hardware differences do.
    """
    assert MODALITIES[name]["primary_axis"]


def test_the_inventory_reports_measurable_and_missing_separately():
    inventory = modality_inventory()
    assert set(inventory["modalities"]) == set(MODALITIES)
    for name, entry in inventory["modalities"].items():
        assert isinstance(entry["measurable"], bool), name
        if not entry["measurable"]:
            assert entry["missing"], f"{name} is not measurable and does not say why"


def test_the_inventory_warns_against_reading_these_as_token_rates():
    assert "tokens per second" in modality_inventory()["note"]


def test_embedding_batches_start_at_one_and_span_an_order_of_magnitude():
    """Batch 1 is the number people quote and the one nobody uses.

    Including it is what makes the batching speedup visible instead of
    implied.
    """
    assert DEFAULT_EMBED_BATCHES[0] == 1
    assert max(DEFAULT_EMBED_BATCHES) >= 32


def test_an_unreachable_endpoint_is_reported_rather_than_measured():
    from aihwbench.modalities import measure_embedding_throughput

    report = measure_embedding_throughput(
        "nomic-embed-text", (1,), host="http://127.0.0.1:1", timeout=2.0
    )
    assert report["unresolved"]
    assert report["batches"] == []


def test_the_cli_exposes_the_inventory():
    import inspect

    from aihwbench.cli import benchmark

    source = inspect.getsource(benchmark)
    assert "modality_inventory()" in source
    assert "measure_embedding_throughput(" in source
