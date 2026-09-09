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
