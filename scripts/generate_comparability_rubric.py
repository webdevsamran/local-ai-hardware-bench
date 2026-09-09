"""Generate the published comparison-safety rubric from the classifier itself.

Usage:
    python scripts/generate_comparability_rubric.py           # write
    python scripts/generate_comparability_rubric.py --check   # verify freshness

The classifier is this project's most distinctive claim, and an undocumented
rule set is indistinguishable from an arbitrary one: a reader cannot predict a
verdict, and a submitter cannot argue with it. So the rubric is published.

It is generated rather than hand-written for the same reason the competitor
table is: a rubric that describes a previous version of the code is worse than
no rubric, because it is believed. CI runs this with --check, so the document
and `aihwbench/comparability.py` cannot disagree.
"""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aihwbench.comparability import (  # noqa: E402
    _CONDITIONAL,
    _REQUIRED_PRESENT,
    _STRICT,
    CONDITIONALLY_COMPARABLE,
    INSUFFICIENT_METADATA,
    NOT_COMPARABLE,
    STRICTLY_COMPARABLE,
)
from aihwbench.trust import TRUST_DEFINITIONS, TRUST_STATES  # noqa: E402

OUT = ROOT / "docs" / "comparability-rubric.md"
NL = chr(10)

# Why each strict field is load-bearing. A bare field list tells a reader what
# the rule is but not why, and the "why" is what makes it auditable.
_WHY: dict[str, str] = {
    "model.name": "A different model is a different experiment.",
    "model.checksum": "Same name, different weights is a different model.",
    "model.format": "GGUF and ONNX of the same model are different artifacts.",
    "model.quantization": "Precision changes both speed and output.",
    "model.revision": "A re-release under the same name is different weights.",
    "model.tokenizer": "Different tokenization means different token counts, so tokens/s is not the same unit.",
    "runtime.name": "Different engines make different trade-offs; this is the comparison people most want and least may make casually.",
    "runtime.backend": "CUDA and DirectML are different execution paths.",
    "runtime.device": "CPU and GPU results are not interchangeable.",
    "reproducibility.workload_type": "Prefill-heavy and decode-heavy runs measure different things.",
    "reproducibility.prompt": "A different prompt is a different amount of work.",
    "reproducibility.max_tokens": "Generation length changes the amortization of prefill.",
    "reproducibility.temperature": "Sampling changes the work done per token.",
    "reproducibility.seed": "An unseeded run is not reproducible.",
    "reproducibility.context_length": "Context size drives KV cache and memory pressure.",
    "reproducibility.batch_size": "Batching changes throughput fundamentally.",
    "reproducibility.concurrency": "Concurrent load measures serving capacity, not single-stream latency.",
    "reproducibility.warmup_runs": "Unwarmed runs include load and compile time.",
    "reproducibility.iterations": "One iteration and fifty are not the same measurement.",
}

_WHY_CONDITIONAL: dict[str, str] = {
    "reproducibility.power_profile": "A different power plan changes clocks, but the experiment is otherwise the same.",
    "system.os_version": "A patch level can move performance without invalidating the comparison.",
    "runtime.version": "Engine versions change performance; the comparison is still meaningful if stated.",
}


def _rows(fields: tuple[str, ...], why: dict[str, str]) -> str:
    return NL.join(
        f"| `{field}` | {why.get(field, 'Materially changes what was measured.')} |"
        for field in fields
    )


def render() -> str:
    parts = [
        "# Comparison-safety rubric",
        "",
        "> **Generated from `aihwbench/comparability.py` by",
        "> `scripts/generate_comparability_rubric.py`. Do not edit by hand.**",
        "> CI verifies it matches the code, so the rule set and this page",
        "> cannot drift apart.",
        "",
        "Two benchmark numbers are only worth comparing when the things they",
        "measured were the same in every way that matters. This page states",
        "exactly when this project considers a comparison safe, so that a",
        "verdict is predictable before you run anything and auditable",
        "afterwards.",
        "",
        "The classifier never decides a winner. It decides only whether a",
        "comparison may honestly be made at all.",
        "",
        "## Verdicts",
        "",
        "| Verdict | Meaning |",
        "| --- | --- |",
        f"| `{STRICTLY_COMPARABLE}` | Every materially relevant dimension matches. The numbers may be compared directly. |",
        f"| `{CONDITIONALLY_COMPARABLE}` | The experiment matches, but something worth stating differs. Compare with the caveat attached. |",
        f"| `{NOT_COMPARABLE}` | The runs measured different things, or did not record enough to tell. A direct comparison would mislead. |",
        "",
        "## Rule 1 — required provenance",
        "",
        "These must be **present on both sides**. If either is missing the",
        f"verdict is `{NOT_COMPARABLE}` with the machine reason",
        f"`{INSUFFICIENT_METADATA}`, whatever else agrees.",
        "",
        "Absence of evidence is not evidence of sameness: two results that",
        "record nothing agree about nothing. Without this rule two empty",
        f"documents classified as `{STRICTLY_COMPARABLE}` — the strongest",
        "verdict, on no evidence at all.",
        "",
        "| Field | |",
        "| --- | --- |",
        _rows(_REQUIRED_PRESENT, _WHY),
        "",
        "This list is deliberately shorter than Rule 2. Results legitimately",
        "omit fields that do not apply to them — an image-classification run",
        "has no prompt, seed or temperature — and requiring those would mark",
        "honest results incomparable.",
        "",
        "## Rule 2 — dimensions that block comparison",
        "",
        f"If any of these **differ**, the verdict is `{NOT_COMPARABLE}`.",
        "Where both sides omit a field, they agree about it and it does not",
        "block; where one side has it and the other does not, they differ.",
        "",
        "| Field | Why it is load-bearing |",
        "| --- | --- |",
        _rows(_STRICT, _WHY),
        "",
        "## Rule 3 — dimensions that downgrade",
        "",
        "If any of these differ (and nothing in Rule 1 or 2 applies), the",
        f"verdict is `{CONDITIONALLY_COMPARABLE}`: the comparison is still",
        "meaningful, but the difference must travel with it.",
        "",
        "| Field | Why it is a caveat, not a blocker |",
        "| --- | --- |",
        _rows(_CONDITIONAL, _WHY_CONDITIONAL),
        "",
        "## Rule 4 — different hardware",
        "",
        "Differing `system.cpu` or `system.gpu` adds the machine reason",
        "`system.hardware` and downgrades to",
        f"`{CONDITIONALLY_COMPARABLE}`. It does not block: comparing hardware",
        "is the entire purpose of the dataset. The caveat exists so a",
        "cross-platform number is read as a cross-platform number.",
        "",
        "## Trust states",
        "",
        "Comparability is about whether two runs measured the same thing.",
        "Trust is a separate question — how much the project vouches for a",
        "result — and the two are never conflated. A `verified` result and an",
        f"`unreviewed` one can be `{STRICTLY_COMPARABLE}`; that says nothing",
        "about whether either is correct.",
        "",
        "| State | Meaning |",
        "| --- | --- |",
        NL.join(f"| `{state}` | {TRUST_DEFINITIONS[state]} |" for state in TRUST_STATES),
        "",
        "## Using it",
        "",
        "```bash",
        "aihwbench compare a.json b.json      # exits 3 when NOT_COMPARABLE",
        "aihwbench regression --baseline ref candidate.json",
        "```",
        "",
        "Both commands exit non-zero rather than printing a comparison the",
        "rubric forbids. `--force` overrides, and still reports the true",
        "verdict so a forced run cannot be mistaken for a clean one.",
        "",
        "## Disagreeing with a verdict",
        "",
        "These rules encode a judgement about what makes two measurements the",
        "same experiment, and a judgement can be wrong. If a rule blocks a",
        "comparison that should be allowed, or permits one that should not,",
        "that is worth raising: see [disputes.md](disputes.md).",
        "",
    ]
    return NL.join(parts) + NL


def main() -> int:
    text = render()
    if "--check" in sys.argv:
        if not OUT.is_file():
            print(f"error: {OUT} is missing; run this script without --check", file=sys.stderr)
            return 1
        if OUT.read_text(encoding="utf-8") != text:
            print(
                f"error: {OUT} is stale. The comparability rules changed without "
                "regenerating the published rubric. Run: "
                "python scripts/generate_comparability_rubric.py",
                file=sys.stderr,
            )
            return 1
        print(f"{OUT} matches the classifier")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
