"""Deterministic RAG pipeline: retrieve, rerank, generate — timed separately.

Every local RAG stack spends its wall-clock in three places, and a single
end-to-end number cannot tell them apart. A machine that feels slow because
retrieval is scanning a large corpus needs a different fix from one that is
slow because the model is slow, and the difference is invisible unless the
three are measured apart. That decomposition is the point of this workload,
the same reason the agentic workload separates LLM time from tool time.

Retrieval and reranking here are **deterministic, local and dependency-free**:
lexical scoring over a bundled corpus, no embedding model and no vector
database. That is a deliberate limit rather than an oversight. Bringing in an
embedding model would measure that model's speed as well, and bringing in a
vector store would measure someone's index build — neither is the hardware
under test, and both would make the workload non-reproducible across machines.

What this measures is the *shape* of a RAG request: a long retrieved context
assembled and fed to the model, with the retrieval and assembly cost visible
next to the generation cost. What it deliberately does not measure is
retrieval *quality*; a lexical retriever is not a stand-in for a good one, and
this module never reports one as if it were.
"""

from __future__ import annotations

import math
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "CORPUS",
    "Passage",
    "retrieve",
    "rerank",
    "run_rag_pipeline",
    "RAG_QUESTIONS",
]

_WORD = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class Passage:
    """One retrievable chunk of the bundled corpus."""

    doc_id: str
    text: str


def _tokens(text: str) -> list[str]:
    return _WORD.findall(text.lower())


# A small technical corpus. Bundled as data rather than read from the
# repository, so the workload measures the same thing on every machine
# regardless of what the checkout contains.
_RAW_DOCS: dict[str, str] = {
    "vram": (
        "VRAM is the single most important specification for local inference. "
        "Model weights must fit in GPU memory, and whatever remains holds the "
        "KV cache. When a model does not fit, layers are offloaded to system "
        "RAM and throughput collapses rather than degrading smoothly."
    ),
    "quantization": (
        "Quantization reduces the precision of model weights. Q4_K_M stores "
        "roughly four bits per weight and cuts memory by about seventy-five "
        "percent against sixteen-bit floats. Lower precision is faster and "
        "also changes what the model outputs, so speed and quality must be "
        "reported together."
    ),
    "kv_cache": (
        "The KV cache stores attention keys and values for every token in "
        "context. It grows linearly with context length. Quantizing the KV "
        "cache is a memory optimisation rather than a speed optimisation: it "
        "buys context length or headroom when sixteen-bit does not fit."
    ),
    "speculative": (
        "Speculative decoding runs a small draft model ahead of the target "
        "model and verifies its guesses in batches. The acceptance rate of "
        "those draft tokens determines whether it helps at all; a low "
        "acceptance rate wastes the draft model's compute entirely."
    ),
    "thermals": (
        "Sustained load raises temperature until the processor throttles. A "
        "thirty-second burst measurement and a thirty-minute sustained "
        "measurement can differ substantially on a laptop, which is why "
        "time-to-throttle matters more than peak throughput there."
    ),
    "power": (
        "Energy per token is only meaningful against an idle baseline. A "
        "reading of two hundred watts on a card that idles at one hundred and "
        "fifty means something very different from the same reading on a card "
        "that idles at twenty."
    ),
    "comparability": (
        "Two benchmark numbers are only comparable when the model, "
        "quantization, runtime, device and workload all match. Comparing "
        "results that differ on any of those measures different experiments "
        "and reports the difference as a performance gap."
    ),
    "batching": (
        "Batching multiple sequences raises total throughput while raising "
        "per-request latency. Single-stream latency and aggregate serving "
        "capacity are different questions and are not interchangeable."
    ),
}

#: The corpus, chunked one passage per document.
CORPUS: tuple[Passage, ...] = tuple(
    Passage(doc_id=key, text=text) for key, text in sorted(_RAW_DOCS.items())
)

#: Questions the pipeline answers, chosen so each has clearly relevant
#: passages and clearly irrelevant ones — otherwise reranking measures nothing.
RAG_QUESTIONS: tuple[str, ...] = (
    "Why does throughput collapse when a model does not fit in VRAM?",
    "Is quantizing the KV cache a speed optimisation or a memory one?",
    "What determines whether speculative decoding helps?",
    "Why is energy per token meaningless without an idle baseline?",
)


def _idf(corpus: tuple[Passage, ...]) -> dict[str, float]:
    """Inverse document frequency over the corpus.

    Without it, a passage matching only common words outranks one matching the
    rare word that actually carries the question.
    """
    counts: dict[str, int] = {}
    for passage in corpus:
        for term in set(_tokens(passage.text)):
            counts[term] = counts.get(term, 0) + 1
    total = len(corpus)
    return {term: math.log(1 + total / (1 + count)) for term, count in counts.items()}


def retrieve(question: str, corpus: tuple[Passage, ...] = CORPUS, top_k: int = 4) -> list[Passage]:
    """Lexical retrieval: the ``top_k`` passages scoring highest for the query.

    Deliberately not semantic. An embedding model would measure that model's
    speed alongside the hardware, and would make results depend on which
    embedding model each contributor happened to have.
    """
    idf = _idf(corpus)
    query = set(_tokens(question))
    scored: list[tuple[float, int, Passage]] = []
    for index, passage in enumerate(corpus):
        terms = _tokens(passage.text)
        if not terms:
            continue
        overlap = sum(idf.get(term, 0.0) for term in terms if term in query)
        # Normalised by length, so a long passage does not win on volume.
        score = overlap / math.sqrt(len(terms))
        # Index breaks ties deterministically; without it, equal scores order
        # arbitrarily and the workload stops being reproducible.
        scored.append((-score, index, passage))
    scored.sort(key=lambda item: (item[0], item[1]))
    return [passage for _score, _index, passage in scored[:top_k]]


def rerank(question: str, passages: list[Passage]) -> list[Passage]:
    """Reorder retrieved passages by exact-phrase proximity to the question.

    A second, more expensive pass over a small candidate set is the shape a
    real reranker has, and it is that shape — not this scoring function — that
    the timing is measuring.
    """
    query_terms = _tokens(question)
    bigrams = {f"{a} {b}" for a, b in zip(query_terms, query_terms[1:], strict=False)}

    def score(passage: Passage) -> tuple[float, str]:
        text = passage.text.lower()
        hits = sum(1 for bigram in bigrams if bigram in text)
        return (-float(hits), passage.doc_id)

    return sorted(passages, key=score)


def build_prompt(question: str, passages: list[Passage]) -> str:
    """Assemble the retrieved context into a single prompt."""
    context = "\n\n".join(f"[{p.doc_id}] {p.text}" for p in passages)
    return (
        "Answer the question using only the context below. "
        "If the context does not contain the answer, say so.\n\n"
        f"Context:\n{context}\n\nQuestion: {question}\nAnswer:"
    )


@dataclass
class RagTrace:
    """Accumulates the three phases of a RAG request."""

    retrieve_ms: list[float] = field(default_factory=list)
    rerank_ms: list[float] = field(default_factory=list)
    generate_ms: list[float] = field(default_factory=list)
    prompt_chars: list[int] = field(default_factory=list)
    _started: float = field(default_factory=time.perf_counter)

    def summarize(self) -> dict[str, Any]:
        elapsed_ms = (time.perf_counter() - self._started) * 1000.0
        retrieve_total = sum(self.retrieve_ms)
        rerank_total = sum(self.rerank_ms)
        generate_total = sum(self.generate_ms)
        measured = retrieve_total + rerank_total + generate_total
        # A sequential pipeline cannot finish faster than its parts; anchoring
        # to the larger keeps overhead non-negative and shares within [0, 1].
        total = max(elapsed_ms, measured)
        queries = len(self.generate_ms)

        def share(value: float) -> float | None:
            return round(value / total, 4) if total > 0 else None

        return {
            "queries": queries,
            "end_to_end_ms": round(total, 3),
            "wall_clock_ms": round(elapsed_ms, 3),
            "retrieval_ms": round(retrieve_total, 3),
            "rerank_ms": round(rerank_total, 3),
            "generation_ms": round(generate_total, 3),
            "overhead_ms": round(max(0.0, total - measured), 3),
            "retrieval_share": share(retrieve_total),
            "rerank_share": share(rerank_total),
            "generation_share": share(generate_total),
            "mean_prompt_chars": (
                round(sum(self.prompt_chars) / len(self.prompt_chars), 1)
                if self.prompt_chars
                else None
            ),
            "note": (
                "retrieval is lexical and local by design; this measures the "
                "shape and cost of a RAG request, never retrieval quality"
            ),
        }


def run_rag_pipeline(
    generate: Callable[[str], str],
    questions: tuple[str, ...] = RAG_QUESTIONS,
    top_k: int = 4,
) -> dict[str, Any]:
    """Run the pipeline over ``questions``, timing each phase separately.

    ``generate`` is the model call. Everything else is fixed, so two runs on
    different hardware differ only in how fast retrieval, reranking and the
    model were.
    """
    trace = RagTrace()
    for question in questions:
        started = time.perf_counter()
        candidates = retrieve(question, top_k=top_k)
        trace.retrieve_ms.append((time.perf_counter() - started) * 1000.0)

        started = time.perf_counter()
        ordered = rerank(question, candidates)
        trace.rerank_ms.append((time.perf_counter() - started) * 1000.0)

        prompt = build_prompt(question, ordered)
        trace.prompt_chars.append(len(prompt))

        started = time.perf_counter()
        generate(prompt)
        trace.generate_ms.append((time.perf_counter() - started) * 1000.0)

    return trace.summarize()
