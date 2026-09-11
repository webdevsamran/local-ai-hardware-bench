"""`model.tokenizer` is in the classifier's strict set and was always null.

The schema declares the field. `comparability._STRICT` reads it. No backend
ever wrote one, so every result this project has published carries
`tokenizer: null` -- and `_same(None, None)` is True by design, which means
two runs whose tokenizers differ have always agreed about their tokenizers.

This is the same shape as `model.quantization`, which was hardcoded to None
while Ollama's API had been returning it all along: a strict field that has
never once discriminated. It matters because changing a tokenizer changes what
a token *is*, so tokens per second stops meaning the same thing -- and unlike
a quantization change, it leaves no trace in the model's name.
"""

from __future__ import annotations

from aihwbench.gguf import tokenizer_identity


def test_the_identity_is_built_from_what_the_header_states():
    identity = tokenizer_identity(
        {
            "tokenizer.ggml.model": "gpt2",
            "tokenizer.ggml.pre": "qwen2",
            "tokenizer.ggml.bos_token_id": 151643,
            "tokenizer.ggml.eos_token_id": 151645,
        }
    )
    assert identity == "gpt2/qwen2/bos:151643/eos:151645"


def test_a_different_tokenizer_family_is_a_different_identity():
    base = {"tokenizer.ggml.model": "gpt2", "tokenizer.ggml.pre": "qwen2"}
    other = {**base, "tokenizer.ggml.model": "llama"}
    assert tokenizer_identity(base) != tokenizer_identity(other)


def test_a_different_pre_tokenizer_is_a_different_identity():
    """The case a model name cannot show.

    Two builds of the same weights with different pre-tokenizers tokenize the
    same prompt into different numbers of tokens, so their throughput figures
    are not comparable even though every other field matches.
    """
    base = {"tokenizer.ggml.model": "gpt2", "tokenizer.ggml.pre": "qwen2"}
    other = {**base, "tokenizer.ggml.pre": "llama-bpe"}
    assert tokenizer_identity(base) != tokenizer_identity(other)


def test_a_changed_end_of_sequence_token_is_a_different_identity():
    """A changed EOS changes where generation stops, and so how much work ran."""
    base = {"tokenizer.ggml.model": "gpt2", "tokenizer.ggml.eos_token_id": 151645}
    other = {**base, "tokenizer.ggml.eos_token_id": 2}
    assert tokenizer_identity(base) != tokenizer_identity(other)


def test_no_tokenizer_metadata_yields_none_rather_than_a_constant():
    """A null is honest; a constant assembled from missing parts is not.

    The same empty string in every result would look like agreement to a
    classifier that reads this field strictly -- which is exactly the failure
    being fixed, reintroduced in a new shape.
    """
    assert tokenizer_identity({}) is None
    assert tokenizer_identity({"tokenizer.ggml.model": None}) is None
    assert tokenizer_identity({"tokenizer.ggml.model": ""}) is None


def test_a_partial_identity_still_carries_what_is_known():
    """A header stating only the family is worth more than nothing."""
    assert tokenizer_identity({"tokenizer.ggml.model": "gpt2"}) == "gpt2"


def test_the_reference_model_reads_the_same_through_both_runtimes():
    """One model must not look like two different tokenizers.

    The identity deliberately excludes the vocabulary array, which a GGUF file
    carries and Ollama's API nulls. Including it would give llama.cpp and
    Ollama different identities for byte-identical weights, and split the
    corpus into halves that cannot be compared.
    """
    from aihwbench.gguf import _TOKENIZER_KEYS

    assert not any("tokens" in key or "merges" in key for key in _TOKENIZER_KEYS), (
        "the identity must not depend on arrays only one runtime exposes"
    )


def test_both_backends_record_a_tokenizer():
    """The field has to be *written*, not merely computable.

    This repository's recurring defect is a capability that is built, tested,
    exported and never reached by production code -- which is precisely what
    kept this field null while the classifier read it.
    """
    import inspect

    from aihwbench.backends import llama_cpp, ollama

    llama_source = inspect.getsource(llama_cpp)
    assert '"tokenizer": read_gguf_tokenizer(' in llama_source

    ollama_source = inspect.getsource(ollama)
    assert '"tokenizer": model_tokenizer(' in ollama_source


def test_the_classifier_still_reads_the_field_it_is_now_given():
    from aihwbench.comparability import _STRICT

    assert "model.tokenizer" in _STRICT


def test_two_results_with_different_tokenizers_are_not_strictly_comparable():
    """End to end: the value written must reach a verdict.

    Before this, both sides were null, `_same(None, None)` was True, and the
    pair compared as STRICTLY_COMPARABLE with no mention of the tokenizer.
    """
    from aihwbench.comparability import STRICTLY_COMPARABLE, compare_classification

    def _result(tokenizer: str | None) -> dict:
        return {
            "model": {"name": "m", "checksum": "sha256:abc", "tokenizer": tokenizer},
            "runtime": {"name": "llama.cpp", "backend": "cuda", "device": "cuda"},
            "reproducibility": {"iterations": 8, "warmup_runs": 3},
        }

    verdict = compare_classification(
        _result("gpt2/qwen2/bos:151643/eos:151645"),
        _result("llama/llama-bpe/bos:1/eos:2"),
    )
    assert verdict["classification"] != STRICTLY_COMPARABLE
    assert any("tokenizer" in reason for reason in verdict["reasons"])


def test_matching_tokenizers_do_not_add_a_reason():
    from aihwbench.comparability import compare_classification

    def _result() -> dict:
        return {
            "model": {"name": "m", "checksum": "sha256:abc", "tokenizer": "gpt2/qwen2"},
            "runtime": {"name": "llama.cpp", "backend": "cuda", "device": "cuda"},
            "reproducibility": {"iterations": 8, "warmup_runs": 3},
        }

    verdict = compare_classification(_result(), _result())
    assert not any("tokenizer" in reason for reason in verdict["reasons"])
