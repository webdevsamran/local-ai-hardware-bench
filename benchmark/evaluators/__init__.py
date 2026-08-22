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
    "register_evaluator",
    "get_evaluator",
    "list_evaluators",
    "discover_evaluator_plugins",
    "load_dataset",
    "run_evaluation",
]

ENTRY_POINT_GROUP = "aihwbench.evaluators"


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
