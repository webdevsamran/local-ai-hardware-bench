"""The RAG pipeline workload.

Every local RAG stack spends wall-clock in three places, and one end-to-end
number cannot separate them: a machine slow because retrieval is scanning a
corpus needs a different fix from one slow because the model is slow.

Retrieval is lexical and local on purpose. An embedding model would measure
that model's speed alongside the hardware, and a vector store would measure
someone's index build -- neither is the hardware under test, and both would
make the workload irreproducible across machines.
"""

from __future__ import annotations

import time

import pytest

from aihwbench.rag import (
    CORPUS,
    RAG_QUESTIONS,
    build_prompt,
    rerank,
    retrieve,
    run_rag_pipeline,
)


def _fake_model(delay_s: float = 0.0):
    def generate(_prompt: str) -> str:
        if delay_s:
            time.sleep(delay_s)
        return "an answer"

    return generate


# ------------------------------------------------------------- retrieval


def test_retrieval_finds_the_relevant_passage_first():
    hits = retrieve("Why does throughput collapse when a model does not fit in VRAM?")
    assert hits[0].doc_id == "vram"


def test_retrieval_is_question_specific():
    """Different questions must surface different passages, or it retrieves nothing."""
    spec = retrieve("What determines whether speculative decoding helps?")
    vram = retrieve("Why does throughput collapse when a model does not fit in VRAM?")
    assert spec[0].doc_id == "speculative"
    assert spec[0].doc_id != vram[0].doc_id


def test_retrieval_is_deterministic():
    """Ties are broken by index; without that the workload is irreproducible."""
    question = RAG_QUESTIONS[0]
    assert [p.doc_id for p in retrieve(question)] == [p.doc_id for p in retrieve(question)]


def test_retrieval_respects_top_k():
    assert len(retrieve(RAG_QUESTIONS[0], top_k=2)) == 2
    assert len(retrieve(RAG_QUESTIONS[0], top_k=len(CORPUS) + 5)) == len(CORPUS)


def test_reranking_is_deterministic_and_preserves_the_candidate_set():
    question = RAG_QUESTIONS[1]
    candidates = retrieve(question)
    first = rerank(question, candidates)
    assert [p.doc_id for p in first] == [p.doc_id for p in rerank(question, candidates)]
    assert {p.doc_id for p in first} == {p.doc_id for p in candidates}


def test_the_prompt_contains_the_retrieved_context_and_the_question():
    question = RAG_QUESTIONS[0]
    prompt = build_prompt(question, retrieve(question))
    assert question in prompt
    assert "[vram]" in prompt


# --------------------------------------------------------- decomposition


def test_the_three_phases_are_timed_separately():
    report = run_rag_pipeline(_fake_model(delay_s=0.01))
    assert report["queries"] == len(RAG_QUESTIONS)
    assert report["retrieval_ms"] > 0
    assert report["rerank_ms"] > 0
    assert report["generation_ms"] > 0


def test_a_slow_model_shows_up_as_generation_time():
    """The distinction the decomposition exists to make."""
    report = run_rag_pipeline(_fake_model(delay_s=0.02))
    assert report["generation_share"] > report["retrieval_share"]


def test_shares_are_a_fraction_of_the_whole():
    report = run_rag_pipeline(_fake_model(0.005))
    total = report["retrieval_share"] + report["rerank_share"] + report["generation_share"]
    assert 0.0 < total <= 1.0


def test_overhead_is_reported_rather_than_absorbed():
    report = run_rag_pipeline(_fake_model())
    parts = (
        report["retrieval_ms"]
        + report["rerank_ms"]
        + report["generation_ms"]
        + report["overhead_ms"]
    )
    assert parts == pytest.approx(report["end_to_end_ms"], abs=1.0)


def test_the_pipeline_never_claims_to_measure_retrieval_quality():
    """A lexical retriever is not a stand-in for a good one, and says so."""
    report = run_rag_pipeline(_fake_model())
    assert "never retrieval quality" in report["note"]


def test_the_pipeline_uses_no_network_modules():
    import ast
    from pathlib import Path

    from aihwbench import rag

    imported: set[str] = set()
    for node in ast.walk(ast.parse(Path(rag.__file__).read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert not (imported & {"urllib", "requests", "socket", "http", "httpx"})


def test_the_rag_workload_is_registered():
    from aihwbench.workloads import get_workload, list_workloads

    assert "rag_pipeline" in list_workloads()
    assert get_workload("rag_pipeline").kind == "combined"


@pytest.mark.parametrize(
    "workload_id",
    [
        "code_completion_fim",
        "long_document_summary",
        "structured_output",
        "streaming_chat_interactivity",
        "rag_pipeline",
    ],
)
def test_new_workloads_describe_what_they_measure(workload_id):
    """A workload without a description is a name nobody can choose between."""
    from aihwbench.workloads import get_workload

    assert len(get_workload(workload_id).description) > 60
