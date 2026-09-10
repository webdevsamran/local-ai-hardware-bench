"""Built-in workloads registered by default.

Includes prefill/decode/combined variants (#11), a growing-context
multi-turn conversation (#14), and a weighted mixed-traffic workload (#13).
Prompt synthesis for target ISL uses a documented ~4-chars-per-token
approximation; the *actual* token counts are always measured by the runtime
and recorded per iteration — targets shape requests, they are never
reported as measurements.
"""

from __future__ import annotations

import random

from . import TrafficMixItem, TurnSpec, Workload, register

NL = chr(10)

__all__ = [
    "synthesize_prompt",
    "sample_traffic_mix",
    "build_multi_turn_prompts",
]

# Documented approximation used only to *shape* prompts. Real token counts
# come from the runtime's tokenizer and are recorded in results.
_CHARS_PER_TOKEN = 4

_BASE_SENTENCE = (
    "Local AI inference performance depends on memory bandwidth, compute "
    "throughput, quantization format, and the runtime's kernel efficiency. "
)


def synthesize_prompt(target_tokens: int, seed: int = 42) -> str:
    """Build a deterministic prompt of approximately ``target_tokens`` tokens.

    Deterministic for a given (target_tokens, seed) so any machine can
    reproduce the exact same request bytes.
    """
    if target_tokens <= 0:
        raise ValueError("target_tokens must be positive")
    rng = random.Random(f"aihwbench-prompt-{target_tokens}-{seed}")
    sentences = [_BASE_SENTENCE] + [
        f"Variation {i}: kernels, batching, and cache behavior shift the "
        "balance between prefill and decode phases on different hardware. "
        for i in range(64)
    ]
    parts: list[str] = []
    length = 0
    while length < target_tokens:
        s = rng.choice(sentences)
        parts.append(s)
        length += max(1, len(s) // _CHARS_PER_TOKEN)
    return "".join(parts).strip()


def sample_traffic_mix(
    mix: tuple[TrafficMixItem, ...], index: int, seed: int = 42
) -> tuple[int, int]:
    """Deterministically pick an (isl, osl) pair from a weighted mix.

    Uses a fixed-seed PRNG walked by request ``index`` so the sequence of
    shapes is identical across machines and runs.
    """
    if not mix:
        raise ValueError("traffic mix must not be empty")
    rng = random.Random(f"aihwbench-mix-{seed}")
    # Burn `index` draws to walk the stream deterministically.
    for _ in range(index):
        _pick(mix, rng)
    return _pick(mix, rng)


def _pick(mix: tuple[TrafficMixItem, ...], rng: random.Random) -> tuple[int, int]:
    roll = rng.random()
    cumulative = 0.0
    for item in mix:
        cumulative += item.weight
        if roll < cumulative:
            return item.isl_tokens, item.osl_tokens
    return mix[-1].isl_tokens, mix[-1].osl_tokens


def build_multi_turn_prompts(turns: tuple[TurnSpec, ...]) -> list[str]:
    """Render each turn as a full conversation transcript.

    Context grows turn-by-turn: turn N includes all previous user turns and
    assistant replies, so latency/memory can be tracked as context expands.
    """
    if not turns:
        raise ValueError("multi-turn workload requires at least one turn")
    nl = chr(10)
    blank = nl + nl
    transcripts: list[str] = []
    history: list[tuple[str, str]] = []
    for i, turn in enumerate(turns):
        lines: list[str] = []
        for j, (user, assistant) in enumerate(history, start=1):
            lines.append(f"[Turn {j} user]{nl}{user}")
            lines.append(f"[Turn {j} assistant]{nl}{assistant}")
        lines.append(f"[Turn {i + 1} user]{nl}{turn.user_prompt}")
        lines.append("[assistant]")
        transcripts.append(blank.join(lines))
        # The scripted assistant reply keeps context growth deterministic;
        # real deployments would append the model's actual reply.
        history.append((turn.user_prompt, f"(scripted reply {i + 1})"))
    return transcripts


# ---------------------------------------------------------------------------
# Built-in registrations
# ---------------------------------------------------------------------------

register(
    Workload(
        id="default_chat",
        kind="generation",
        description="Default single-request chat benchmark (schema 1.0 compatible).",
        prompt="Explain what a token is in large language models, in two sentences.",
        osl_tokens=128,
    )
)

register(
    Workload(
        id="sustained_generation",
        kind="generation",
        description=(
            "Long-form generation with a concrete prompt, for measuring decode "
            "throughput at steady state. Unlike the decode_only and "
            "long_generation profiles, which declare a target output length "
            "but carry no prompt to elicit it, this one runs as-is."
        ),
        # `default_chat` asks for an answer "in two sentences", so it generates
        # about 29 tokens however high max_tokens is set. That is too little
        # work to measure a generation *rate*: on the reference machine the
        # per-iteration figure ran 327, 342, 118, 124, 84 tok/s as the GPU
        # ramped its clocks, giving a 56% coefficient of variation around a
        # mean the machine never actually sustained.
        #
        # This prompt asks for output long enough to reach and hold a steady
        # state, so the mean describes a rate rather than a ramp. It is a
        # separate workload rather than a change to `default_chat`, because
        # the prompt is part of the comparison key: editing the default would
        # silently redefine what every existing published result measured.
        prompt=(
            "Write a detailed technical explanation of how transformer "
            "language models process text, covering tokenization, embeddings, "
            "self-attention, feed-forward layers, and autoregressive decoding. "
            "Explain each stage thoroughly and in order, with concrete detail."
        ),
        osl_tokens=512,
    )
)

register(
    Workload(
        id="prefill_only",
        kind="prefill",
        description="Prefill-heavy: long input, minimal generation (prompt processing rate).",
        isl_tokens=2048,
        osl_tokens=1,
    )
)

register(
    Workload(
        id="decode_only",
        kind="decode",
        description="Decode-heavy: short input, long generation (token generation rate).",
        isl_tokens=32,
        osl_tokens=512,
    )
)

register(
    Workload(
        id="mixed_traffic_realistic",
        kind="combined",
        description=(
            "Weighted ISL/OSL traffic mix approximating realistic chat traffic: "
            "60% short/short, 25% long-prompt/short, 15% short/long."
        ),
        traffic_mix=(
            TrafficMixItem(weight=0.60, isl_tokens=256, osl_tokens=256),
            TrafficMixItem(weight=0.25, isl_tokens=2048, osl_tokens=128),
            TrafficMixItem(weight=0.15, isl_tokens=256, osl_tokens=1024),
        ),
    )
)

register(
    Workload(
        id="multi_turn_8",
        kind="multi_turn",
        description=(
            "Eight-turn conversation with growing context; measures latency, "
            "throughput, and memory as context expands turn-by-turn."
        ),
        turns=tuple(
            TurnSpec(
                user_prompt=(
                    f"Question {i}: summarize the key trade-offs of running LLMs locally "
                    f"on consumer hardware, part {i} of 8."
                ),
                expected_output_tokens=96,
            )
            for i in range(1, 9)
        ),
    )
)

register(
    Workload(
        id="agentic_swe",
        kind="agentic",
        description=(
            "Software-engineering agent: a fixed four-step loop of search and "
            "file reads, reporting LLM inference time and tool execution time "
            "separately. Tools are local and deterministic, and the sequence "
            "is scripted rather than model-chosen, so the loop is identical "
            "on every machine."
        ),
        osl_tokens=64,
        requires=("tool_calls",),
    )
)

register(
    Workload(
        id="agentic_data_analyst",
        kind="agentic",
        description=(
            "Data-analyst agent: reads a bundled table and summarizes it, "
            "reporting LLM inference time and tool execution time separately."
        ),
        osl_tokens=64,
        requires=("tool_calls",),
    )
)

# ---------------------------------------------------------------------------
# Task-shaped workloads
#
# Each has a distinct request *shape* rather than merely a distinct prompt: a
# code-completion request is short-in/short-out and latency-bound, a
# summarization request is long-in/short-out and prefill-bound, and the two
# stress different parts of a machine. Registering them separately is what lets
# a published result say which shape it measured.

_FIM_PROMPT = (
    "Complete the middle of this function."
    + NL
    + NL
    + "def parse_duration(text: str) -> float:"
    + NL
    + "    # Seconds from a string like '2h30m' or '90s'."
    + NL
    + "    total = 0.0"
    + NL
    + "    # <FILL>"
    + NL
    + "    return total"
    + NL
)

register(
    Workload(
        id="code_completion_fim",
        kind="generation",
        description=(
            "Fill-in-the-middle code completion: short prefix and suffix, "
            "short completion. Latency-bound, and the shape an editor "
            "integration actually issues -- time to first token matters far "
            "more here than sustained throughput."
        ),
        prompt=_FIM_PROMPT,
        osl_tokens=64,
    )
)

register(
    Workload(
        id="long_document_summary",
        kind="prefill",
        description=(
            "Long-document summarization: a large input reduced to a short "
            "answer. Prefill-bound, and the workload where context-depth "
            "scaling and KV-cache pressure show up first."
        ),
        isl_tokens=8192,
        osl_tokens=192,
    )
)

register(
    Workload(
        id="structured_output",
        kind="generation",
        description=(
            "Structured output / function calling: the model must emit "
            "parseable JSON. Pairs with the json_validity evaluator, which "
            "scores whether the output actually parsed rather than whether it "
            "merely looked plausible."
        ),
        prompt=(
            'Return a JSON object with keys "model", "quantization" and '
            '"vram_gb" describing a 7B model at Q4_K_M on a 12 GB card. '
            "Reply with JSON only."
        ),
        osl_tokens=96,
        requires=("structured_output",),
    )
)

register(
    Workload(
        id="streaming_chat_interactivity",
        kind="generation",
        description=(
            "Interactive chat: a short prompt and a long streamed reply. Read "
            "for inter-token latency spread rather than mean throughput, "
            "because one long pause mid-response feels far worse than a "
            "uniformly slower stream at the same average rate."
        ),
        isl_tokens=64,
        osl_tokens=768,
        requires=("streaming",),
    )
)

register(
    Workload(
        id="rag_pipeline",
        kind="combined",
        description=(
            "Retrieval-augmented generation: retrieve, rerank and generate, "
            "each timed separately. Retrieval is lexical and local by design, "
            "so the workload measures the machine rather than someone's "
            "embedding model or vector index."
        ),
        osl_tokens=192,
    )
)
