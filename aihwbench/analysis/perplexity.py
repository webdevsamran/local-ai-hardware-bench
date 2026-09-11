"""Perplexity, and the reason most published perplexity comparisons are void.

Perplexity is the standard number for "did quantization hurt this model", and
it is the standard number people compare across models that cannot be compared.
It is a per-*token* quantity. Two models with different tokenizers cut the same
text into different numbers of tokens, so their perplexities are computed over
different denominators and the comparison means nothing -- while looking
exactly like a comparison that means something, because both are small
positive numbers and one is smaller.

So every measurement here records what it was measured over: the tokenizer
identity, the corpus hash, the context length and the chunk count. Change any
of them and the numbers stop being comparable; `perplexity_comparable` says so
rather than leaving a reader to notice.

The corpus is supplied by the caller. This repository bundles no restricted
datasets, and a perplexity figure over a corpus nobody names is not a result.

Perplexity is also one of the few quality figures that can be measured on a
machine too busy to benchmark on: it is a deterministic function of the model
and the text, so contention changes how long it takes and not what it is.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path
from typing import Any

__all__ = [
    "measure_perplexity",
    "parse_perplexity_output",
    "perplexity_comparable",
    "PERPLEXITY_COMPARABILITY_KEYS",
]

#: `Final estimate: PPL = 29.6384 +/- 2.15127`
_FINAL_ESTIMATE = re.compile(
    r"Final\s+estimate:\s*PPL\s*=\s*([0-9]+\.?[0-9]*)\s*\+/-\s*([0-9]+\.?[0-9]*)",
    re.IGNORECASE,
)

#: `perplexity: calculating perplexity over 8 chunks, n_ctx=512, ...`
_RUN_SHAPE = re.compile(
    r"calculating\s+perplexity\s+over\s+(\d+)\s+chunks,\s*n_ctx\s*=\s*(\d+)",
    re.IGNORECASE,
)

#: Everything that has to match before two perplexities may be compared.
#:
#: `tokenizer` is the one people omit. Perplexity is per token, so a model that
#: splits the corpus into fewer tokens is being asked an easier question --
#: and the resulting number is smaller for a reason that has nothing to do
#: with quality.
PERPLEXITY_COMPARABILITY_KEYS = (
    "tokenizer",
    "corpus_sha256",
    "context_length",
    "chunks",
)


def parse_perplexity_output(text: str) -> dict[str, Any]:
    """Pull the figures out of `llama-perplexity` output.

    Returns nulls rather than raising when the run produced no estimate: a
    model that failed to load has no perplexity, and inventing one would be
    worse than reporting the absence.
    """
    final = _FINAL_ESTIMATE.search(text or "")
    shape = _RUN_SHAPE.search(text or "")
    return {
        "perplexity": float(final.group(1)) if final else None,
        "perplexity_stderr": float(final.group(2)) if final else None,
        "chunks": int(shape.group(1)) if shape else None,
        "context_length": int(shape.group(2)) if shape else None,
    }


def _corpus_digest(path: Path) -> str | None:
    digest = hashlib.sha256()
    try:
        with open(path, "rb") as handle:
            while chunk := handle.read(1 << 20):
                digest.update(chunk)
    except OSError:
        return None
    return f"sha256:{digest.hexdigest()}"


def measure_perplexity(
    model_path: str | Path,
    corpus_path: str | Path,
    *,
    context_length: int = 512,
    chunks: int | None = None,
    gpu_layers: int = 99,
    binary: str | None = None,
    timeout: float = 3600.0,
) -> dict[str, Any]:
    """Measure perplexity over a corpus, recording what makes it comparable.

    Runs llama.cpp's `llama-perplexity`. Returns a report whose
    `comparable_against` block is what another measurement must match before
    the two numbers may be put beside each other.
    """
    from ..backends.llama_cpp import _find_binary
    from ..gguf import read_gguf_tokenizer

    model_path = Path(model_path)
    corpus_path = Path(corpus_path)

    executable = binary or _find_binary("llama-perplexity")
    if not executable:
        return {
            "perplexity": None,
            "unresolved": (
                "llama-perplexity was not found. It ships with llama.cpp; "
                "perplexity cannot be computed without a runtime that exposes "
                "per-token logits, which the HTTP server does not."
            ),
        }
    if not corpus_path.is_file():
        return {"perplexity": None, "unresolved": f"no corpus at {corpus_path}"}

    command = [
        executable,
        "-m",
        str(model_path),
        "-f",
        str(corpus_path),
        "-c",
        str(context_length),
        "-ngl",
        str(gpu_layers),
    ]
    if chunks is not None:
        command += ["--chunks", str(chunks)]

    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"perplexity": None, "unresolved": f"llama-perplexity did not run: {exc}"}

    parsed = parse_perplexity_output((proc.stdout or "") + (proc.stderr or ""))
    if parsed["perplexity"] is None:
        return {
            **parsed,
            "unresolved": (
                f"llama-perplexity exited {proc.returncode} without reporting an estimate"
            ),
        }

    return {
        **parsed,
        "model_path_name": model_path.name,
        # What another measurement has to match. Recorded with the number
        # rather than remembered alongside it, because the comparison is made
        # by whoever reads the two files later.
        "comparable_against": {
            "tokenizer": read_gguf_tokenizer(model_path),
            "corpus_sha256": _corpus_digest(corpus_path),
            "context_length": parsed["context_length"],
            "chunks": parsed["chunks"],
        },
        "unresolved": None,
    }


def perplexity_comparable(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    """Whether two perplexity measurements may be placed beside each other.

    The same shape of answer the comparison-safety classifier gives for
    benchmark results, for the same reason: the interesting failure is not a
    wrong number but a valid number compared against the wrong thing.

    A differing tokenizer is fatal and gets said plainly, because it is the
    mistake this function exists for. Perplexity is per token; a model whose
    tokenizer produces fewer tokens for the same text is answering an easier
    question, and its lower perplexity is not evidence of a better model.
    """
    a = left.get("comparable_against") or {}
    b = right.get("comparable_against") or {}
    reasons: list[str] = []
    unknown: list[str] = []

    for key in PERPLEXITY_COMPARABILITY_KEYS:
        first, second = a.get(key), b.get(key)
        if first is None or second is None:
            unknown.append(key)
        elif first != second:
            reasons.append(key)

    detail = None
    if "tokenizer" in reasons:
        detail = (
            "the two models tokenize differently, so their perplexities are "
            "computed over different numbers of tokens. The smaller number is "
            "not the better model; the two are not on the same scale at all."
        )
    elif "corpus_sha256" in reasons:
        detail = "measured over different text, so the two numbers describe different tasks"

    return {
        "comparable": not reasons and not unknown,
        "differs": reasons,
        # Unknown is not agreement. A measurement that did not record its
        # tokenizer cannot be shown to be comparable, which is a different
        # statement from being incomparable.
        "unknown": unknown,
        "detail": detail
        or (
            f"cannot be shown comparable: {unknown} not recorded on both sides" if unknown else None
        ),
    }
