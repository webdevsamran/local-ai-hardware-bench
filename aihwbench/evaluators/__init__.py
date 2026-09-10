"""Accuracy/evaluation framework (#16, #17).

Evaluators score *quality* separately from performance. They never feed
into performance numbers and never collapse into a single opaque score.

Design:
- ``Evaluator`` subclasses implement ``evaluate(response, expected) ->
  EvaluatorScore``.
- Built-in evaluators are deterministic and dependency-free: exact match,
  JSON validity (function-calling format), and cosine similarity over
  caller-supplied embedding vectors.
- Datasets are user-supplied JSONL files ({"input": ..., "expected": ...});
  the repository bundles no restricted datasets.
- Third-party evaluators publish via the ``aihwbench.evaluators``
  entry-point group.
"""

from __future__ import annotations

import importlib.metadata
import json
import math
import re
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

__all__ = [
    "EvaluatorScore",
    "Evaluator",
    "ExactMatchEvaluator",
    "JsonValidityEvaluator",
    "CosineSimilarityEvaluator",
    "RougeLEvaluator",
    "TokenF1Evaluator",
    "register_evaluator",
    "get_evaluator",
    "list_evaluators",
    "discover_evaluator_plugins",
    "load_dataset",
    "run_evaluation",
]

ENTRY_POINT_GROUP = "aihwbench.evaluators"

#: Word tokens for the overlap evaluators. Digits are kept, because a wrong
#: number is a wrong answer.
_WORD_RE = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class EvaluatorScore:
    """One quality measurement. ``score`` is in [0, 1] or None if N/A."""

    evaluator: str
    score: float | None
    detail: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"evaluator": self.evaluator, "score": self.score, "detail": self.detail}


class Evaluator(Protocol):
    name: str

    def evaluate(self, response: str, expected: str | None = None) -> EvaluatorScore: ...


class ExactMatchEvaluator:
    """Deterministic exact-match after whitespace normalization."""

    name = "exact_match"

    def evaluate(self, response: str, expected: str | None = None) -> EvaluatorScore:
        if expected is None:
            return EvaluatorScore(self.name, None, "no expected value supplied")
        score = 1.0 if " ".join(response.split()) == " ".join(expected.split()) else 0.0
        return EvaluatorScore(self.name, score)


class JsonValidityEvaluator:
    """Checks the response parses as JSON (function-calling format check)."""

    name = "json_validity"

    def evaluate(self, response: str, expected: str | None = None) -> EvaluatorScore:
        try:
            json.loads(response)
        except (json.JSONDecodeError, TypeError):
            return EvaluatorScore(self.name, 0.0, "response is not valid JSON")
        return EvaluatorScore(self.name, 1.0)


def _tokens(text: str) -> list[str]:
    """Lower-cased word tokens, punctuation dropped.

    The normalisation both evaluators below share. SQuAD's own scorer also
    strips articles; that is a decision about English grading conventions
    rather than about text overlap, so it is left out and stated rather than
    applied silently.
    """
    return _WORD_RE.findall(text.lower())


def _lcs_length(left: list[str], right: list[str]) -> int:
    """Longest common subsequence length, in O(len(left) x len(right)) time.

    Two rows rather than a full table: summaries are long enough that the
    quadratic table costs real memory, and only the previous row is ever read.
    """
    if not left or not right:
        return 0
    previous = [0] * (len(right) + 1)
    for l_token in left:
        current = [0] * (len(right) + 1)
        for j, r_token in enumerate(right, start=1):
            if l_token == r_token:
                current[j] = previous[j - 1] + 1
            else:
                current[j] = max(previous[j], current[j - 1])
        previous = current
    return previous[-1]


class RougeLEvaluator:
    """ROUGE-L F1: longest-common-subsequence overlap with a reference.

    The standard summarisation measure, and one of the quality signals the
    closest academic competitor reports where this project had none. It scores
    whether the response covers the reference's content *in order*, which is
    what distinguishes a summary from a bag of the right words.

    It is an overlap statistic, not a judgement of quality: a response can
    score well while being wrong, and a good paraphrase using different words
    scores badly. That is inherent to ROUGE and the reason it is reported
    beside other evaluators rather than as "the" quality number.

    No dataset is bundled. References come from the caller's JSONL, so
    nothing here depends on a licence this repository cannot grant.
    """

    name = "rouge_l"

    def evaluate(self, response: str, expected: str | None = None) -> EvaluatorScore:
        if expected is None:
            return EvaluatorScore(self.name, None, "no reference summary supplied")
        candidate = _tokens(response)
        reference = _tokens(expected)
        if not candidate or not reference:
            # An empty side makes precision or recall undefined rather than
            # zero, and reporting 0.0 would read as "scored, and scored badly".
            return EvaluatorScore(
                self.name, None, "response or reference contains no words to compare"
            )
        overlap = _lcs_length(candidate, reference)
        if overlap == 0:
            return EvaluatorScore(self.name, 0.0, "no common subsequence")
        precision = overlap / len(candidate)
        recall = overlap / len(reference)
        f1 = 2 * precision * recall / (precision + recall)
        return EvaluatorScore(
            self.name,
            round(f1, 6),
            f"lcs={overlap} precision={precision:.3f} recall={recall:.3f}",
        )


class TokenF1Evaluator:
    """SQuAD-style token overlap F1, order-insensitive.

    The measure extractive question-answering is graded with: how much of the
    reference answer's vocabulary the response recovered, and how much of the
    response was in the reference. Unlike ROUGE-L it ignores order, which is
    the right choice for a short factual answer and the wrong one for a
    summary -- the two exist side by side because they answer different
    questions.

    Repeated words count once each, matching SQuAD's multiset intersection:
    saying "Paris Paris Paris" does not earn three times the credit for
    "Paris".
    """

    name = "token_f1"

    def evaluate(self, response: str, expected: str | None = None) -> EvaluatorScore:
        if expected is None:
            return EvaluatorScore(self.name, None, "no expected answer supplied")
        candidate = _tokens(response)
        reference = _tokens(expected)
        if not candidate or not reference:
            return EvaluatorScore(
                self.name, None, "response or expected answer contains no words to compare"
            )
        common = Counter(candidate) & Counter(reference)
        overlap = sum(common.values())
        if overlap == 0:
            return EvaluatorScore(self.name, 0.0, "no shared tokens")
        precision = overlap / len(candidate)
        recall = overlap / len(reference)
        f1 = 2 * precision * recall / (precision + recall)
        return EvaluatorScore(
            self.name,
            round(f1, 6),
            f"matched={overlap} precision={precision:.3f} recall={recall:.3f}",
        )


class CosineSimilarityEvaluator:
    """Cosine similarity between response and reference embedding vectors.

    Vectors are supplied by the caller (e.g. from the runtime's embedding
    endpoint); this evaluator performs only the math.
    """

    name = "embedding_cosine"

    def evaluate(self, response: str, expected: str | None = None) -> EvaluatorScore:
        raise NotImplementedError(
            "use evaluate_vectors(response_vec, reference_vec) for embeddings"
        )

    def evaluate_vectors(
        self, response_vec: list[float], reference_vec: list[float]
    ) -> EvaluatorScore:
        if len(response_vec) != len(reference_vec) or not response_vec:
            return EvaluatorScore(self.name, None, "vector length mismatch")
        dot = sum(a * b for a, b in zip(response_vec, reference_vec, strict=True))
        na = math.sqrt(sum(a * a for a in response_vec))
        nb = math.sqrt(sum(b * b for b in reference_vec))
        if na == 0.0 or nb == 0.0:
            return EvaluatorScore(self.name, None, "zero-magnitude vector")
        return EvaluatorScore(self.name, dot / (na * nb))


_REGISTRY: dict[str, Evaluator] = {
    ExactMatchEvaluator.name: ExactMatchEvaluator(),
    JsonValidityEvaluator.name: JsonValidityEvaluator(),
    CosineSimilarityEvaluator.name: CosineSimilarityEvaluator(),
    RougeLEvaluator.name: RougeLEvaluator(),
    TokenF1Evaluator.name: TokenF1Evaluator(),
}
_PLUGINS_DISCOVERED = False


def register_evaluator(evaluator: Evaluator) -> Evaluator:
    _REGISTRY[evaluator.name] = evaluator
    return evaluator


def get_evaluator(name: str) -> Evaluator:
    _ensure_plugins()
    try:
        return _REGISTRY[name]
    except KeyError:
        known = ", ".join(sorted(_REGISTRY)) or "<none>"
        raise KeyError(f"unknown evaluator {name!r}; registered: {known}") from None


def list_evaluators() -> list[str]:
    _ensure_plugins()
    return sorted(_REGISTRY)


def discover_evaluator_plugins() -> Iterator[tuple[str, Evaluator]]:
    global _PLUGINS_DISCOVERED
    eps = importlib.metadata.entry_points()
    try:
        group = eps.select(group=ENTRY_POINT_GROUP)
    except AttributeError:
        group = eps.get(ENTRY_POINT_GROUP, [])  # type: ignore[attr-defined]
    for ep in group:
        try:
            obj = ep.load()
            evaluator = obj() if callable(obj) and not hasattr(obj, "name") else obj
            if hasattr(evaluator, "name") and hasattr(evaluator, "evaluate"):
                yield register_evaluator(evaluator).name, evaluator
        except Exception:
            continue
    _PLUGINS_DISCOVERED = True


def _ensure_plugins() -> None:
    if not _PLUGINS_DISCOVERED:
        for _ in discover_evaluator_plugins():
            pass


def load_dataset(path: Path) -> list[dict[str, Any]]:
    """Load a user-supplied JSONL evaluation dataset.

    Each line: {"input": str, "expected": str | null}. No datasets are
    bundled with the repository; users supply their own legally usable data.
    """
    items: list[dict[str, Any]] = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{i + 1}: invalid JSONL: {exc}") from exc
        if not isinstance(obj, dict) or "input" not in obj:
            raise ValueError(f"{path}:{i + 1}: each line needs an 'input' field")
        items.append(obj)
    return items


def run_evaluation(
    evaluator_name: str,
    responses: list[str],
    expected: list[str | None] | None = None,
) -> dict[str, Any]:
    """Evaluate responses; returns per-item scores plus the mean.

    Mean is None when no item produced a score — never a fabricated 0.
    """
    evaluator = get_evaluator(evaluator_name)
    expected = expected or [None] * len(responses)
    scores: list[float] = []
    details: list[dict[str, Any]] = []
    for response, exp in zip(responses, expected, strict=False):
        result = evaluator.evaluate(response, exp)
        details.append(result.as_dict())
        if result.score is not None:
            scores.append(result.score)
    return {
        "evaluator": evaluator_name,
        "items": details,
        "mean_score": (sum(scores) / len(scores)) if scores else None,
        "scored_items": len(scores),
        "total_items": len(responses),
    }
