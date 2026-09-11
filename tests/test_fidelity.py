"""Output fidelity, and the refusal to publish speed without it.

Lowering weight precision makes a model faster and also changes what it says.
A quantization table that reports only tokens-per-second therefore leads a
reader to a worse configuration while looking like data. This is the one
output the project must not produce by accident.
"""

from __future__ import annotations

from aihwbench.fidelity import output_fidelity
from aihwbench.quantization import compare_quantizations, has_quality_signal


def test_identical_outputs_are_deterministic():
    report = output_fidelity(["the same answer", "the same answer", "the same answer"])
    assert report["deterministic"] is True
    assert report["distinct_outputs"] == 1
    assert report["iterations_captured"] == 3
    assert report["output_hash"].startswith("sha256:")


def test_differing_outputs_are_not_deterministic():
    """At temperature 0 with a fixed seed this means the run is unreliable."""
    report = output_fidelity(["answer one", "answer two"])
    assert report["deterministic"] is False
    assert report["distinct_outputs"] == 2


def test_the_same_text_always_hashes_the_same():
    a = output_fidelity(["identical text"])
    b = output_fidelity(["identical text"])
    assert a["output_hash"] == b["output_hash"]


def test_different_text_hashes_differently():
    a = output_fidelity(["one"])
    b = output_fidelity(["two"])
    assert a["output_hash"] != b["output_hash"]


def test_a_runtime_that_emits_no_text_says_so():
    """Graph runtimes generate no tokens; that is not a fidelity failure."""
    report = output_fidelity([None, None])
    assert report["deterministic"] is None
    assert report["output_hash"] is None
    assert "emits none" in report["reason"]


def test_empty_strings_are_not_counted_as_output():
    """Counting empty strings would report a false identity across runs."""
    report = output_fidelity(["", ""])
    assert report["iterations_captured"] == 0
    assert report["deterministic"] is None


def test_evaluator_score_stays_null_without_a_dataset():
    """A fabricated accuracy score is worse than an absent one."""
    report = output_fidelity(["some text"])
    assert report["mean_score"] is None
    assert report["evaluators"] == {}


# ------------------------------------------------------- quantization tables


def _result(quant: str, tps: float, output_hash: str | None) -> dict:
    doc = {
        "run_id": f"run-{quant}",
        "model": {"name": "llama-3-8b", "quantization": quant},
        "metrics": {"generation_tokens_per_second": tps},
    }
    if output_hash is not None:
        doc["quality"] = {"output_hash": output_hash, "deterministic": True}
    return doc


def test_speed_only_comparison_has_no_quality_signal():
    comparison = compare_quantizations([_result("q4_k_m", 80.0, None)])
    assert has_quality_signal(comparison) is False


def test_output_hash_counts_as_a_quality_signal():
    comparison = compare_quantizations([_result("q4_k_m", 80.0, "sha256:abc")])
    assert has_quality_signal(comparison) is True


def test_variants_are_compared_against_the_highest_precision_output():
    """The faster variant that changed the output must be visible as such."""
    comparison = compare_quantizations(
        [
            _result("q4_k_m", 80.0, "sha256:different"),
            _result("fp16", 30.0, "sha256:reference"),
            _result("q8_0", 55.0, "sha256:reference"),
        ]
    )
    rows = {r["quantization"]: r for r in comparison["families"]["llama"]}
    assert rows["q4_k_m"]["reference_quantization"] == "fp16"
    # Fastest, but it does not say the same thing as the reference.
    assert rows["q4_k_m"]["same_output_as_reference"] is False
    # Slower than q4_k_m, yet identical to the reference output.
    assert rows["q8_0"]["same_output_as_reference"] is True
    assert rows["fp16"]["same_output_as_reference"] is True


def test_agreement_is_unknown_rather_than_assumed_without_a_hash():
    comparison = compare_quantizations(
        [_result("fp16", 30.0, "sha256:reference"), _result("q4_0", 90.0, None)]
    )
    rows = {r["quantization"]: r for r in comparison["families"]["llama"]}
    assert rows["q4_0"]["same_output_as_reference"] is None


def test_no_reference_when_nothing_was_hashed():
    comparison = compare_quantizations([_result("q4_0", 90.0, None)])
    row = comparison["families"]["llama"][0]
    assert row["reference_quantization"] is None
    assert row["same_output_as_reference"] is None


# --- how much quality a quantization gives up, as a number ------------------
#
# `same_output_as_reference` answers yes/no: did this variant say exactly the
# same thing? That is the right question for a determinism check and the wrong
# one for choosing a quantization, because every useful quantization answers
# "no" and the answer carries no magnitude. Someone choosing between q8_0 and
# q4_k_m needs to know whether the gap is 0.005 or 0.08.


def _variant(quant: str, tps: float, score: float | None = None, out_hash: str | None = None):
    quality: dict = {}
    if score is not None:
        quality["mean_score"] = score
    if out_hash is not None:
        quality["output_hash"] = out_hash
    return {
        "run_id": f"r-{quant}",
        "model": {"name": "m", "quantization": quant, "format": "gguf"},
        "metrics": {"generation_tokens_per_second": tps},
        "quality": quality,
    }


def _rows(*variants):
    from aihwbench.quantization import compare_quantizations

    families = compare_quantizations(list(variants))["families"]
    rows = next(iter(families.values()))
    return {r["quantization"]: r for r in rows}


def test_the_delta_is_measured_against_the_highest_precision_scored_variant():
    rows = _rows(
        _variant("fp16", 100.0, 0.91),
        _variant("q8_0", 150.0, 0.905),
        _variant("q4_k_m", 220.0, 0.83),
    )
    assert rows["fp16"]["quality_delta_vs_reference"] == 0.0
    assert rows["q8_0"]["quality_delta_vs_reference"] == -0.005
    assert rows["q4_k_m"]["quality_delta_vs_reference"] == -0.08
    assert rows["q4_k_m"]["quality_reference_quantization"] == "fp16"


def test_an_unevaluated_variant_is_unknown_not_equal_to_the_reference():
    """A missing score compared as zero would rank it alongside fp16.

    That is the recommendation a speed-only table makes, arrived at by a
    different route.
    """
    rows = _rows(_variant("fp16", 100.0, 0.91), _variant("q4_0", 240.0))
    assert rows["q4_0"]["quality_delta_vs_reference"] is None
    assert rows["q4_0"]["quality_mean_score"] is None


def test_no_scored_variant_means_no_deltas_rather_than_a_fabricated_baseline():
    rows = _rows(_variant("fp16", 100.0), _variant("q4_0", 240.0))
    assert all(r["quality_delta_vs_reference"] is None for r in rows.values())
    assert all(r["quality_reference_quantization"] is None for r in rows.values())


def test_the_score_baseline_is_chosen_independently_of_the_hash_baseline():
    """A run may carry an output hash and no score, or the reverse.

    Taking the highest-precision *hashed* row as the score baseline would
    compare every delta against a row that has no score, yielding nulls
    everywhere and hiding a signal that was actually present.
    """
    rows = _rows(
        # Highest precision, hashed, but never evaluated.
        _variant("fp16", 100.0, None, "h-fp16"),
        _variant("q8_0", 150.0, 0.90, "h-q8"),
        _variant("q4_k_m", 220.0, 0.82, "h-q4"),
    )
    assert rows["q8_0"]["quality_reference_quantization"] == "q8_0"
    assert rows["q8_0"]["quality_delta_vs_reference"] == 0.0
    assert rows["q4_k_m"]["quality_delta_vs_reference"] == -0.08
    # The hash baseline is still the highest-precision hashed row.
    assert rows["q4_k_m"]["reference_quantization"] == "fp16"


def test_a_quantization_that_scores_higher_gets_a_positive_delta():
    """Not impossible, and not something to quietly clamp to zero.

    Evaluator noise and genuine quantization-as-regularization both produce
    it; a reader seeing +0.01 should see +0.01.
    """
    rows = _rows(_variant("fp16", 100.0, 0.90), _variant("q8_0", 150.0, 0.91))
    assert rows["q8_0"]["quality_delta_vs_reference"] > 0
