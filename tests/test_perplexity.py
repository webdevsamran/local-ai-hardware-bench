"""Perplexity is easy to measure and easy to compare wrongly.

It is a per-*token* quantity. Two models with different tokenizers cut the same
text into different numbers of tokens, so their perplexities have different
denominators and the comparison is void -- while looking exactly like a valid
one, because both are small positive numbers and one is smaller.

Measured on the reference model over this repository's own documentation:
4 chunks gave 36.3644 and 8 chunks gave 29.6384. Same model, same corpus, same
context: the chunk count alone moved the figure by 23%. That is why the run
shape is recorded with the number rather than remembered beside it.
"""

from __future__ import annotations

from aihwbench.analysis.perplexity import (
    PERPLEXITY_COMPARABILITY_KEYS,
    parse_perplexity_output,
    perplexity_comparable,
)

REAL_OUTPUT = """
perplexity: tokenizing the input ..
perplexity: calculating perplexity over 8 chunks, n_ctx=512, batch_size=2048, n_seq=4
perplexity: 0.31 seconds per pass - ETA 0.00 minutes
[1]15.5937,[2]22.3444,[3]33.0774,[4]36.3644,[5]37.1009,[6]32.9571,[7]30.2161,[8]29.6384,
Final estimate: PPL = 29.6384 +/- 2.15127
"""


def test_it_reads_the_figures_llama_perplexity_actually_prints():
    parsed = parse_perplexity_output(REAL_OUTPUT)
    assert parsed["perplexity"] == 29.6384
    assert parsed["perplexity_stderr"] == 2.15127
    assert parsed["chunks"] == 8
    assert parsed["context_length"] == 512


def test_a_run_that_produced_no_estimate_yields_none_not_a_number():
    """A model that failed to load has no perplexity.

    Inventing one -- zero, or the last per-chunk figure -- would be a result.
    """
    parsed = parse_perplexity_output("error: failed to load model\n")
    assert parsed["perplexity"] is None
    assert parsed["perplexity_stderr"] is None


def test_partial_output_does_not_yield_a_partial_number():
    """Per-chunk figures are not the estimate.

    The running values are printed as the run proceeds and the last one before
    an interruption is not the answer; only the final estimate is.
    """
    truncated = REAL_OUTPUT[: REAL_OUTPUT.index("Final estimate")]
    assert parse_perplexity_output(truncated)["perplexity"] is None
    # The shape is still readable, which is what says the run started.
    assert parse_perplexity_output(truncated)["chunks"] == 8


def _measurement(**over):
    base = {
        "tokenizer": "gpt2/qwen2/bos:151643/eos:151645",
        "corpus_sha256": "sha256:" + "a" * 64,
        "context_length": 512,
        "chunks": 8,
    }
    base.update(over)
    return {"perplexity": 29.6, "comparable_against": base}


def test_identical_run_shapes_are_comparable():
    verdict = perplexity_comparable(_measurement(), _measurement())
    assert verdict["comparable"] is True
    assert verdict["differs"] == []


def test_a_different_tokenizer_is_named_as_the_reason_it_is_void():
    """The mistake this exists for.

    Comparing a Llama-tokenized perplexity against a Qwen-tokenized one is the
    most common invalid comparison in the literature, and the numbers give no
    hint of it.
    """
    verdict = perplexity_comparable(
        _measurement(), _measurement(tokenizer="llama/llama-bpe/bos:1/eos:2")
    )
    assert verdict["comparable"] is False
    assert verdict["differs"] == ["tokenizer"]
    assert "not the better model" in verdict["detail"]


def test_a_different_corpus_is_a_different_task():
    verdict = perplexity_comparable(
        _measurement(), _measurement(corpus_sha256="sha256:" + "b" * 64)
    )
    assert verdict["comparable"] is False
    assert "different text" in verdict["detail"]


def test_a_different_chunk_count_is_not_comparable():
    """Measured: 4 chunks gave 36.36 where 8 gave 29.64 on the same model.

    A 23% move from the run shape alone would swamp the quality difference
    anyone was trying to detect.
    """
    verdict = perplexity_comparable(_measurement(), _measurement(chunks=4))
    assert verdict["comparable"] is False
    assert verdict["differs"] == ["chunks"]


def test_a_different_context_length_is_not_comparable():
    verdict = perplexity_comparable(_measurement(), _measurement(context_length=2048))
    assert verdict["differs"] == ["context_length"]


def test_an_unrecorded_field_is_unknown_rather_than_agreement():
    """ "Not recorded" and "the same" are different claims.

    A measurement that did not state its tokenizer cannot be *shown*
    comparable, which is not the same as being incomparable -- and treating
    the absence as a match is the `_same(None, None)` hole in another costume.
    """
    verdict = perplexity_comparable(_measurement(), _measurement(tokenizer=None))
    assert verdict["comparable"] is False
    assert verdict["differs"] == []
    assert verdict["unknown"] == ["tokenizer"]


def test_a_measurement_with_no_provenance_block_is_not_comparable():
    verdict = perplexity_comparable({"perplexity": 10.0}, {"perplexity": 11.0})
    assert verdict["comparable"] is False
    assert set(verdict["unknown"]) == set(PERPLEXITY_COMPARABILITY_KEYS)


def test_the_tokenizer_is_part_of_the_contract():
    """Guards against a future tidy-up dropping the field that matters most."""
    assert "tokenizer" in PERPLEXITY_COMPARABILITY_KEYS


def test_a_missing_corpus_is_reported_rather_than_measured(tmp_path):
    from aihwbench.analysis.perplexity import measure_perplexity

    report = measure_perplexity(tmp_path / "model.gguf", tmp_path / "absent.txt")
    assert report["perplexity"] is None
    assert (
        "no corpus" in report["unresolved"]
        or "llama-perplexity was not found" in (report["unresolved"])
    )


def test_the_cli_exposes_it():
    """A capability nothing can reach is this repository's recurring defect."""
    import inspect

    from aihwbench.cli import benchmark

    source = inspect.getsource(benchmark)
    assert "measure_perplexity(" in source
    assert '"perplexity"' in source
