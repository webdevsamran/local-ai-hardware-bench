"""The comparison-safety classifier, pinned where mutation testing found it open.

`aihwbench/comparability.py` decides whether two benchmark results may be
compared at all. It is the mechanism behind this project's central claim --
that a number from one runtime and a number from another differ only in what
they measured. Mutation testing scored it 45.5%: 12 of 22 mutants survived.

Three of the survivors are safety-relevant rather than cosmetic:

  line 130  `Eq -> NotEq`  in `assert_comparable`. Inverting this makes the
                           guard *raise for comparable results and pass
                           NOT_COMPARABLE ones* -- the function permitting
                           exactly what it exists to block, with the suite
                           green.
  line  67  `False -> True` in `_same`. When one value is present and the
                           other missing, this returns False (not the same).
                           Flipped, a result missing a field would count as
                           matching any value, so a run with no recorded seed
                           would compare "safely" against one with a seed.
  line  64  `and -> or`    in `_same`'s both-None check, which would make a
                           single None mean "identical".

The classifier is fail-closed by design; these tests hold it that way.
"""

from __future__ import annotations

import pytest

from aihwbench.comparability import (
    CONDITIONALLY_COMPARABLE,
    NOT_COMPARABLE,
    STRICTLY_COMPARABLE,
    _same,
    assert_comparable,
    compare_classification,
)


def result(**overrides: object) -> dict:
    """A minimal but complete result document, overridable by dotted path."""
    base = {
        "model": {
            "name": "llama-3-8b",
            "checksum": "sha256:abc",
            "format": "gguf",
            "quantization": "Q4_K_M",
            "revision": "1",
            "tokenizer": "llama-bpe",
        },
        "runtime": {
            "name": "llama.cpp",
            "backend": "cuda",
            "device": "gpu0",
            "version": "b4938",
        },
        "reproducibility": {
            "workload_type": "generation",
            "prompt": "hello",
            "max_tokens": 128,
            "temperature": 0.0,
            "seed": 42,
            "context_length": 4096,
            "batch_size": 1,
            "concurrency": 1,
            "warmup_runs": 2,
            "iterations": 10,
            "power_profile": "balanced",
        },
        "system": {"cpu": "Ryzen 9", "gpu": "RTX 4090", "os_version": "Windows 11"},
    }
    for path, value in overrides.items():
        section, _, key = path.partition("__")
        base[section][key] = value
    return base


# ------------------------------------------------------------------ _same


def test_one_value_missing_is_not_the_same_as_a_value_present() -> None:
    """Kills `False -> True` on `_same`'s mixed-None branch.

    This is the safety-critical direction: if a missing field counted as
    matching, a run that never recorded its seed would compare "strictly" with
    one that did, and the published comparison would be between two different
    experiments.
    """
    assert _same(None, 42) is False
    assert _same(42, None) is False


def test_both_missing_counts_as_the_same() -> None:
    """Kills `and -> or` on the both-None check.

    With `or`, a single None would return True from this branch and never
    reach the mixed-None guard below it.
    """
    assert _same(None, None) is True


def test_equal_values_are_the_same_and_unequal_ones_are_not() -> None:
    assert _same(42, 42) is True
    assert _same(42, 43) is False
    assert _same("a", "a") is True


# ------------------------------------------------- compare_classification


def test_identical_runs_are_strictly_comparable() -> None:
    assert compare_classification(result(), result())["classification"] == STRICTLY_COMPARABLE


@pytest.mark.parametrize(
    ("section", "key", "value"),
    [
        ("model", "name", "mistral-7b"),
        ("model", "checksum", "sha256:def"),
        ("model", "quantization", "Q8_0"),
        ("runtime", "name", "ollama"),
        ("runtime", "backend", "rocm"),
        ("reproducibility", "seed", 7),
        ("reproducibility", "max_tokens", 256),
        ("reproducibility", "iterations", 50),
    ],
)
def test_any_strict_field_differing_blocks_comparison(
    section: str, key: str, value: object
) -> None:
    """Every field in `_STRICT` must be load-bearing, not decorative."""
    other = result()
    other[section][key] = value
    verdict = compare_classification(result(), other)
    assert verdict["classification"] == NOT_COMPARABLE, (
        f"{section}.{key} differing must block comparison"
    )
    # `model.name` is deliberately reported as "models differ: X vs Y" rather
    # than by field path, which is friendlier and still identifies the cause.
    assert any(key in r or "models differ" in r for r in verdict["reasons"]), (
        "the reason must identify what differed"
    )


@pytest.mark.parametrize(
    ("section", "key", "value"),
    [
        ("reproducibility", "power_profile", "performance"),
        ("runtime", "version", "b5000"),
        ("system", "os_version", "Windows 10"),
    ],
)
def test_conditional_fields_downgrade_rather_than_block(
    section: str, key: str, value: object
) -> None:
    other = result()
    other[section][key] = value
    verdict = compare_classification(result(), other)
    assert verdict["classification"] == CONDITIONALLY_COMPARABLE


def test_a_missing_strict_field_on_one_side_blocks_comparison() -> None:
    """The `_same` mixed-None behaviour, seen through the classifier.

    A result that never recorded its seed is not interchangeable with one that
    did, and must not be reported as strictly comparable.
    """
    other = result()
    del other["reproducibility"]["seed"]
    assert compare_classification(result(), other)["classification"] == NOT_COMPARABLE


def test_differing_hardware_is_reported_even_when_otherwise_comparable() -> None:
    other = result()
    other["system"]["gpu"] = "RX 7900"
    verdict = compare_classification(result(), other)
    assert any("hardware differs" in r for r in verdict["reasons"])


# ------------------------------------------------------- assert_comparable


def test_assert_comparable_raises_only_for_not_comparable() -> None:
    """Kills `Eq -> NotEq` on the classification check.

    Inverted, this guard would raise for comparable results and silently
    permit the incomparable ones -- the exact opposite of its purpose, and the
    single most consequential line in this module.
    """
    other = result()
    other["model"]["name"] = "mistral-7b"
    with pytest.raises(ValueError, match="NOT_COMPARABLE"):
        assert_comparable(result(), other)


def test_assert_comparable_permits_identical_runs() -> None:
    """The other side of the inversion: comparable results must not raise.

    The call itself is the assertion; ruff rightly flagged an earlier
    `... is None` here as a comparison that tested nothing.
    """
    assert_comparable(result(), result())


def test_assert_comparable_permits_conditionally_comparable_runs() -> None:
    """Only NOT_COMPARABLE raises; a downgrade is a warning, not a refusal."""
    other = result()
    other["runtime"]["version"] = "b5000"
    assert_comparable(result(), other)


def test_the_error_names_every_reason() -> None:
    """A refusal a reader cannot act on is not much better than a crash."""
    other = result()
    other["model"]["name"] = "mistral-7b"
    other["runtime"]["backend"] = "rocm"
    with pytest.raises(ValueError) as excinfo:
        assert_comparable(result(), other)
    message = str(excinfo.value)
    assert "model.name" in message or "models differ" in message
    assert "runtime.backend" in message
