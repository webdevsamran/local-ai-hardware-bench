"""Speculative decoding: the acceptance rate, which decides whether it helps.

Speculative decoding runs a small draft model ahead of a large one and keeps
whatever the large model agrees with. It is sold as a free ~2x, and whether you
get one depends entirely on a number almost nobody publishes: the **acceptance
rate**, the share of drafted tokens the target model accepts.

The arithmetic is unforgiving. Each verification step costs one target forward
pass regardless of how many draft tokens it checks, plus the draft model's own
passes. At a high acceptance rate you get several tokens for one target pass
and the speedup is real. At a low one you pay for the draft model and throw its
output away — speculative decoding *loses* to plain decoding, and the only
visible symptom is that the promised speedup did not arrive.

The rate is a property of the model pair *and the prompt*. Code and repetitive
text draft well; open-ended prose drafts badly. So a single acceptance figure
without the workload beside it is not transferable, and this records both.

The distinction this module exists for
--------------------------------------

Zero drafted tokens and zero acceptance are different states, and conflating
them is the trap. Measured on the reference machine: llama.cpp loaded the draft
model, logged `common_speculative_init_result: loading draft model`, raised no
warning, served requests normally — and the speculative counters stayed at
zero. Speculation never ran.

Reported as "acceptance rate 0%", that reads as "this draft model is useless"
and sends someone off to find a better one. Reported as "speculation did not
engage", it sends them to their runtime configuration, which is where the
problem is. `acceptance_report` refuses to divide by zero drafts and says which
state it found.
"""

from __future__ import annotations

import re
from typing import Any

__all__ = [
    "SPECULATIVE_METRICS",
    "parse_speculative_metrics",
    "acceptance_report",
    "net_speedup",
]

#: Prometheus counters llama-server exposes with `--metrics`.
SPECULATIVE_METRICS = {
    "draft_tokens": "llamacpp:spec_decode_num_draft_tokens_total",
    "accepted_tokens": "llamacpp:spec_decode_num_accepted_tokens_total",
    "drafts": "llamacpp:spec_decode_num_drafts_total",
}


def _metric_pattern(name: str) -> re.Pattern[str]:
    return re.compile(rf"^{re.escape(name)}(?:\{{[^}}]*\}})?\s+([0-9.eE+-]+)\s*$", re.MULTILINE)


def parse_speculative_metrics(prometheus_text: str) -> dict[str, float | None]:
    """Read the speculative counters from a `/metrics` scrape.

    Missing counters yield None rather than zero: a runtime that does not
    expose them has not told us there were no drafts, and recording a zero
    would be inventing a measurement.
    """
    out: dict[str, float | None] = {}
    for key, metric in SPECULATIVE_METRICS.items():
        match = _metric_pattern(metric).search(prometheus_text or "")
        out[key] = float(match.group(1)) if match else None
    return out


def acceptance_report(
    before: dict[str, float | None],
    after: dict[str, float | None],
    workload: str | None = None,
) -> dict[str, Any]:
    """Acceptance rate for the work done between two scrapes.

    Counters are cumulative, so the figure for one run is the difference. A
    report built from `after` alone would average in every earlier request the
    server handled, which on a long-lived server is most of them.
    """
    deltas: dict[str, float | None] = {}
    for key in SPECULATIVE_METRICS:
        first, second = before.get(key), after.get(key)
        deltas[key] = None if first is None or second is None else second - first

    drafted = deltas.get("draft_tokens")
    accepted = deltas.get("accepted_tokens")
    drafts = deltas.get("drafts")

    if drafted is None or accepted is None:
        return {
            "speculation_engaged": None,
            "acceptance_rate": None,
            "workload": workload,
            "unresolved": (
                "the runtime did not expose speculative counters, so whether it "
                "speculated is unknown. llama-server needs --metrics."
            ),
        }

    if drafted <= 0:
        # The state this module exists to distinguish. Seen on the reference
        # machine: the draft model loaded, nothing warned, and no token was
        # ever drafted.
        return {
            "speculation_engaged": False,
            "acceptance_rate": None,
            "draft_tokens": 0,
            "accepted_tokens": 0,
            "workload": workload,
            "unresolved": (
                "no tokens were drafted, so speculative decoding did not engage. "
                "This is not an acceptance rate of zero: a rate of zero would "
                "mean the draft model was consulted and always wrong, which "
                "sends you looking for a better draft model. Nothing was "
                "consulted. Check that the runtime actually enabled "
                "speculation -- llama.cpp loads the draft model and logs no "
                "warning when it does not."
            ),
        }

    rate = accepted / drafted
    per_draft = (accepted / drafts) if drafts else None
    return {
        "speculation_engaged": True,
        "acceptance_rate": round(rate, 4),
        "draft_tokens": int(drafted),
        "accepted_tokens": int(accepted),
        "verification_steps": int(drafts) if drafts is not None else None,
        # Tokens won per target forward pass. The number that decides whether
        # the arithmetic works out, because each verification step costs one
        # target pass however many draft tokens it checked.
        "accepted_per_verification": round(per_draft, 3) if per_draft is not None else None,
        "workload": workload,
        "caveat": (
            "acceptance is a property of the model pair and the prompt, not of "
            "the hardware. Code and repetitive text draft well; open-ended "
            "prose drafts badly. This figure does not transfer to a different "
            "workload."
        ),
        "unresolved": None,
    }


def net_speedup(
    with_draft: dict[str, Any],
    without_draft: dict[str, Any],
    acceptance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Whether speculation actually paid, measured rather than assumed.

    The only honest test is running the same workload both ways on the same
    machine. An acceptance rate alone does not settle it: the draft model costs
    memory and forward passes, and a high acceptance on a draft model too large
    to be cheap still loses.

    A ratio below 1.0 is a real and common outcome, and is reported as such
    rather than floored — "speculative decoding made this slower" is the
    finding someone needs before they ship it.
    """
    fast = (with_draft or {}).get("generation_tokens_per_second")
    slow = (without_draft or {}).get("generation_tokens_per_second")
    if not isinstance(fast, int | float) or not isinstance(slow, int | float) or slow <= 0:
        return {
            "speedup": None,
            "unresolved": "both runs must report a generation rate to be compared",
        }

    ratio = fast / slow
    draft_vram = (with_draft or {}).get("peak_vram_mb")
    base_vram = (without_draft or {}).get("peak_vram_mb")
    overhead = (
        round(draft_vram - base_vram, 1)
        if isinstance(draft_vram, int | float) and isinstance(base_vram, int | float)
        else None
    )

    report: dict[str, Any] = {
        "speedup": round(ratio, 3),
        "helped": ratio > 1.0,
        "with_draft_tokens_per_second": fast,
        "without_draft_tokens_per_second": slow,
        # What the draft model cost to keep resident. A speedup bought with
        # memory you did not have is not a speedup.
        "draft_memory_overhead_mb": overhead,
        "unresolved": None,
    }
    if acceptance is not None:
        report["acceptance_rate"] = acceptance.get("acceptance_rate")
        if acceptance.get("speculation_engaged") is False:
            report["caveat"] = (
                "speculation did not engage, so this ratio compares two "
                "identical configurations and measures run-to-run noise."
            )
    if ratio <= 1.0:
        report["caveat"] = (
            f"speculative decoding was {1 / ratio:.2f}x SLOWER here. The draft "
            "model's own forward passes and the discarded tokens cost more than "
            "the accepted ones saved."
        )
    return report
