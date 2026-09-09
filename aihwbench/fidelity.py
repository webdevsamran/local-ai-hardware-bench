"""Output-fidelity probe attached to every generative benchmark run.

Reducing weight precision makes a model faster *and* changes what it says.
Publishing tokens-per-second across quantization levels with no signal about
output quality actively misleads readers into choosing a worse configuration,
so a speed number from a quantized run should never travel alone.

The probe here is deliberately the one that needs nothing extra: with a fixed
prompt, temperature 0 and a fixed seed, a run should be *reproducible*, and the
text it produced can be fingerprinted. That gives two measured facts for free
on every run:

- **determinism** — did repeated iterations of an identical request produce
  identical text? Non-determinism at temperature 0 means the configuration
  cannot be compared with anything, including itself.
- **output hash** — a fingerprint of what was generated, so two runs that
  differ only in quantization can be checked for whether they still say the
  same thing.

Neither is an accuracy score, and neither is presented as one. Scored
evaluation against a reference dataset stays in :mod:`aihwbench.evaluators`
and is reported separately in ``evaluators``/``mean_score``; those stay null
until a dataset is actually supplied, because a fabricated score is worse than
an absent one.

The generated text itself is *not* published. It is model output rather than
user data, but it is unbounded in size and unbounded in content, and a hash
answers every question the dataset needs to ask of it.
"""

from __future__ import annotations

import hashlib
from typing import Any

__all__ = ["output_fidelity", "OUTPUT_HASH_PREFIX"]

OUTPUT_HASH_PREFIX = "sha256:"


def _hash(text: str) -> str:
    return OUTPUT_HASH_PREFIX + hashlib.sha256(text.encode("utf-8")).hexdigest()


def output_fidelity(texts: list[str | None]) -> dict[str, Any]:
    """Measure determinism and fingerprint the output of one benchmark run.

    ``texts`` is the generated text of each measured iteration, in order.
    Iterations that captured no text (a graph runtime emits none) are ignored
    rather than counted as empty strings, which would report a false identity.
    """
    captured = [t for t in texts if isinstance(t, str) and t != ""]
    if not captured:
        return {
            "output_hash": None,
            "deterministic": None,
            "distinct_outputs": 0,
            "iterations_captured": 0,
            "output_chars": None,
            "evaluators": {},
            "mean_score": None,
            "reason": "no generated text was captured; this runtime emits none",
        }

    hashes = [_hash(t) for t in captured]
    distinct = sorted(set(hashes))
    return {
        # The first iteration's fingerprint, which is what a cross-quantization
        # comparison checks against.
        "output_hash": hashes[0],
        # At temperature 0 with a fixed seed, identical requests should give
        # identical text. When they do not, the run is not reproducible and no
        # comparison drawn from it is safe.
        "deterministic": len(distinct) == 1,
        "distinct_outputs": len(distinct),
        "iterations_captured": len(captured),
        "output_chars": len(captured[0]),
        # Scored evaluation needs a reference dataset; see aihwbench evaluate.
        "evaluators": {},
        "mean_score": None,
        "reason": None,
    }
