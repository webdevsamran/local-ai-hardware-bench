"""Deterministic agentic workload: tools, and the timing decomposition.

An agent loop spends its wall-clock time in two very different places — waiting
on the model, and running tools — and they scale with completely different
things. A single end-to-end number hides which one dominates, so a machine that
is slow because its GPU is slow looks identical to one that is slow because a
tool blocked on disk. Reporting the two separately is what makes the number
actionable, and it is the decomposition the wider benchmark ecosystem
converged on.

Everything here is deliberately **deterministic and local**:

- Tools run against bundled fixtures, never the network. A benchmark whose
  results depend on someone's DNS, or on a rate limit, is not reproducible.
- The tool sequence is scripted rather than chosen by the model. Small local
  models emit tool calls unreliably, so letting the model drive would measure
  its function-calling accuracy — a real thing to measure, but not hardware
  performance, and it would make the workload non-deterministic between runs.
- Tool outputs are fixed strings, so the prompt fed back to the model on the
  next turn is identical on every machine.

What is measured is real: the model is genuinely called each turn, and the
tools genuinely execute.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "ToolCall",
    "AgenticTrace",
    "TOOLS",
    "run_tool",
    "run_agentic_loop",
    "SWE_AGENT_SCRIPT",
    "DATA_ANALYST_SCRIPT",
    "AGENTIC_SCRIPTS",
]


# --------------------------------------------------------------------- tools
#
# A small corpus the tools operate on. Bundled as data rather than read from
# the repository, so the workload measures the same thing regardless of what
# the checkout happens to contain.

_CORPUS: dict[str, str] = {
    "config.py": (
        "TIMEOUT_SECONDS = 30\n"
        "RETRY_LIMIT = 3\n"
        "CACHE_ENABLED = True\n"
        "def load_config(path):\n"
        "    return {}\n"
    ),
    "server.py": (
        "from config import load_config\n"
        "def handle(request):\n"
        "    config = load_config('config.py')\n"
        "    if request.timeout > TIMEOUT_SECONDS:\n"
        "        raise TimeoutError('request exceeded TIMEOUT_SECONDS')\n"
        "    return 200\n"
    ),
    "metrics.csv": ("day,requests,errors\n1,1200,4\n2,1340,7\n3,980,2\n4,1510,19\n5,1425,3\n"),
}


def _read_file(path: str = "") -> str:
    """Return one bundled file, or an explicit miss."""
    if path in _CORPUS:
        return _CORPUS[path]
    return f"error: no such file {path!r}; available: {', '.join(sorted(_CORPUS))}"


def _search(query: str = "") -> str:
    """Substring search across the corpus, reported deterministically."""
    if not query:
        return "error: empty query"
    hits: list[str] = []
    for name in sorted(_CORPUS):
        for number, line in enumerate(_CORPUS[name].splitlines(), start=1):
            if query in line:
                hits.append(f"{name}:{number}: {line.strip()}")
    return "\n".join(hits) if hits else f"no matches for {query!r}"


def _list_files(pattern: str = "") -> str:
    names = sorted(n for n in _CORPUS if pattern in n)
    return "\n".join(names) if names else f"no files matching {pattern!r}"


def _summarize_csv(path: str = "") -> str:
    """Column totals for a bundled CSV — the data-analyst tool."""
    text = _CORPUS.get(path)
    if text is None:
        return f"error: no such file {path!r}"
    rows = [line.split(",") for line in text.strip().splitlines()]
    header, body = rows[0], rows[1:]
    totals: list[str] = []
    for index, column in enumerate(header):
        values = []
        for row in body:
            try:
                values.append(float(row[index]))
            except (ValueError, IndexError):
                values = []
                break
        if values:
            totals.append(f"{column}: sum={sum(values):.0f} mean={sum(values) / len(values):.1f}")
    return "; ".join(totals) if totals else "no numeric columns"


#: Tool name -> implementation. Deterministic and local by construction.
TOOLS: dict[str, Callable[..., str]] = {
    "read_file": _read_file,
    "search": _search,
    "list_files": _list_files,
    "summarize_csv": _summarize_csv,
}


@dataclass(frozen=True)
class ToolCall:
    """One scripted tool invocation in an agentic script."""

    tool: str
    args: dict[str, Any] = field(default_factory=dict)
    #: What the model is asked once the tool has answered.
    follow_up: str = "Given that result, state the next step in one sentence."


def run_tool(call: ToolCall) -> tuple[str, float]:
    """Execute one tool, returning its output and the elapsed milliseconds.

    An unknown tool returns an error string rather than raising: an agent loop
    that meets a bad tool call keeps going, and the benchmark should measure
    that path rather than abort.
    """
    started = time.perf_counter()
    implementation = TOOLS.get(call.tool)
    if implementation is None:
        output = f"error: unknown tool {call.tool!r}"
    else:
        try:
            output = implementation(**call.args)
        except TypeError as exc:
            output = f"error: bad arguments for {call.tool!r}: {exc}"
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return output, elapsed_ms


# ------------------------------------------------------------------- tracing


@dataclass
class AgenticTrace:
    """Accumulates the two halves of an agent loop's wall-clock time."""

    llm_ms: list[float] = field(default_factory=list)
    tool_ms: list[float] = field(default_factory=list)
    tool_names: list[str] = field(default_factory=list)
    turns: int = 0
    _started: float = field(default_factory=time.perf_counter)

    def record_llm(self, elapsed_ms: float) -> None:
        self.llm_ms.append(elapsed_ms)
        self.turns += 1

    def record_tool(self, name: str, elapsed_ms: float) -> None:
        self.tool_ms.append(elapsed_ms)
        self.tool_names.append(name)

    def summarize(self) -> dict[str, Any]:
        """The decomposition: inference time, tool time, and the remainder.

        ``overhead_ms`` is wall-clock minus the two measured components — the
        loop's own serialization, prompt assembly and bookkeeping. Reporting it
        rather than folding it into either component keeps the two honest: if
        the parts do not add up, the gap is visible instead of absorbed.
        """
        elapsed_ms = (time.perf_counter() - self._started) * 1000.0
        llm_total = sum(self.llm_ms)
        tool_total = sum(self.tool_ms)
        measured = llm_total + tool_total
        # A sequential loop cannot finish in less time than its parts took, so
        # wall-clock below `measured` means the components were not measured
        # against this clock (a replayed trace, or concurrent execution).
        # Anchoring to the larger of the two keeps overhead non-negative and
        # the shares within [0, 1] instead of producing a share above 1.
        total_ms = max(elapsed_ms, measured)
        return {
            "turns": self.turns,
            "tool_calls": len(self.tool_ms),
            "tools_used": sorted(set(self.tool_names)),
            "end_to_end_ms": round(total_ms, 3),
            "wall_clock_ms": round(elapsed_ms, 3),
            "llm_inference_ms": round(llm_total, 3),
            "tool_execution_ms": round(tool_total, 3),
            "overhead_ms": round(max(0.0, total_ms - measured), 3),
            "llm_inference_share": (round(llm_total / total_ms, 4) if total_ms > 0 else None),
            "tool_execution_share": (round(tool_total / total_ms, 4) if total_ms > 0 else None),
            "mean_llm_ms_per_turn": (
                round(llm_total / len(self.llm_ms), 3) if self.llm_ms else None
            ),
            "mean_tool_ms_per_call": (
                round(tool_total / len(self.tool_ms), 3) if self.tool_ms else None
            ),
        }


def run_agentic_loop(
    generate: Callable[[str], str],
    script: tuple[ToolCall, ...],
    system_prompt: str = (
        "You are a software agent. Answer briefly, using only the tool output you are given."
    ),
) -> dict[str, Any]:
    """Run one scripted agent loop, timing the model and the tools separately.

    ``generate`` is the model call: it takes a prompt and returns the
    completion. Everything about the loop other than the model is fixed, so
    two runs of this on different hardware differ only in how fast the model
    and the tools were.

    Timing brackets each half precisely: the model call is timed around
    ``generate``, each tool around its own execution, and whatever remains of
    wall-clock is reported as overhead rather than attributed to either.
    """
    trace = AgenticTrace()
    transcript: list[str] = [system_prompt]

    for call in script:
        output, tool_ms = run_tool(call)
        trace.record_tool(call.tool, tool_ms)

        transcript.append(f"[tool:{call.tool}] {output}")
        transcript.append(f"[user] {call.follow_up}")
        prompt = "\n".join(transcript)

        started = time.perf_counter()
        completion = generate(prompt)
        trace.record_llm((time.perf_counter() - started) * 1000.0)

        transcript.append(f"[assistant] {completion}")

    summary = trace.summarize()
    # The transcript is reproducible from the script and the model, so only
    # its size is published -- the same reasoning that keeps generated text
    # out of a result document.
    summary["transcript_chars"] = sum(len(part) for part in transcript)
    return summary


# ------------------------------------------------------------------- scripts
#
# Two scenarios, chosen to exercise different shapes: a software-engineering
# agent that reads and searches code, and a data-analyst agent that inspects a
# table. Both are fixed sequences so every machine runs the identical loop.

SWE_AGENT_SCRIPT: tuple[ToolCall, ...] = (
    ToolCall(
        tool="search",
        args={"query": "TIMEOUT_SECONDS"},
        follow_up="Which file defines this constant, and which file uses it?",
    ),
    ToolCall(
        tool="read_file",
        args={"path": "config.py"},
        follow_up="State the configured timeout in seconds.",
    ),
    ToolCall(
        tool="read_file",
        args={"path": "server.py"},
        follow_up="Describe in one sentence when this code raises TimeoutError.",
    ),
    ToolCall(
        tool="list_files",
        args={"pattern": ".py"},
        follow_up="List the Python files you have inspected.",
    ),
)

DATA_ANALYST_SCRIPT: tuple[ToolCall, ...] = (
    ToolCall(
        tool="read_file",
        args={"path": "metrics.csv"},
        follow_up="Name the columns in this table.",
    ),
    ToolCall(
        tool="summarize_csv",
        args={"path": "metrics.csv"},
        follow_up="State which day had the most errors.",
    ),
)


#: Workload id -> scripted tool sequence. Registered as workloads in
#: `aihwbench.workloads.builtin`; the scripts live here beside the tools.
AGENTIC_SCRIPTS: dict[str, tuple[ToolCall, ...]] = {
    "agentic_swe": SWE_AGENT_SCRIPT,
    "agentic_data_analyst": DATA_ANALYST_SCRIPT,
}
