"""The agentic workload, and its timing decomposition.

ROADMAP and CHANGELOG claimed deterministic agentic tool-call benchmarks for
some time while `agentic` existed only as a permitted string in a validation
set. These tests hold the claim to the implementation.

An agent loop spends time waiting on the model and time running tools, and the
two scale with unrelated things. A single end-to-end number cannot tell a slow
GPU from a slow tool, so the split is the point of the workload.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from aihwbench.agentic import (
    AGENTIC_SCRIPTS,
    DATA_ANALYST_SCRIPT,
    SWE_AGENT_SCRIPT,
    AgenticTrace,
    ToolCall,
    run_agentic_loop,
    run_tool,
)


def _fake_model(delay_s: float = 0.0):
    def generate(_prompt: str) -> str:
        if delay_s:
            time.sleep(delay_s)
        return "acknowledged"

    return generate


# ----------------------------------------------------------------- the tools


def test_tools_are_deterministic():
    """Two runs of the same call must produce identical output.

    A benchmark whose tool results vary between runs cannot be compared with
    itself, let alone across machines.
    """
    call = ToolCall(tool="search", args={"query": "TIMEOUT_SECONDS"})
    assert run_tool(call)[0] == run_tool(call)[0]


def test_tools_never_touch_the_network():
    """Every tool answers from the bundled corpus.

    A tool that reached the network would make results depend on DNS, latency
    and rate limits -- none of which is the hardware under test.

    Checked against the module's actual imports rather than its text: the
    bundled CSV has a column called "requests", and matching on substrings
    would flag the fixture data instead of a real dependency.
    """
    import ast

    from aihwbench import agentic

    source = Path(agentic.__file__).read_text(encoding="utf-8")
    imported: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])

    networking = {"urllib", "requests", "socket", "http", "httpx", "aiohttp", "ftplib"}
    assert not (imported & networking), (
        f"agentic tools must not import networking modules: {imported & networking}"
    )


def test_unknown_tool_returns_an_error_rather_than_raising():
    """An agent that hits a bad tool call keeps going; so must the benchmark."""
    output, elapsed = run_tool(ToolCall(tool="does_not_exist"))
    assert "unknown tool" in output
    assert elapsed >= 0.0


def test_bad_arguments_are_reported_not_raised():
    output, _ = run_tool(ToolCall(tool="read_file", args={"nope": 1}))
    assert "bad arguments" in output


def test_search_finds_across_files_in_a_stable_order():
    output, _ = run_tool(ToolCall(tool="search", args={"query": "TIMEOUT_SECONDS"}))
    lines = output.splitlines()
    assert lines[0].startswith("config.py:")
    assert any(line.startswith("server.py:") for line in lines)


def test_summarize_csv_computes_real_totals():
    output, _ = run_tool(ToolCall(tool="summarize_csv", args={"path": "metrics.csv"}))
    assert "errors: sum=35" in output


# ------------------------------------------------------------ decomposition


def test_loop_separates_model_time_from_tool_time():
    """The headline requirement: the two halves are reported separately."""
    report = run_agentic_loop(_fake_model(delay_s=0.01), SWE_AGENT_SCRIPT)
    assert report["turns"] == len(SWE_AGENT_SCRIPT)
    assert report["tool_calls"] == len(SWE_AGENT_SCRIPT)
    # The model was deliberately made the slow half.
    assert report["llm_inference_ms"] > report["tool_execution_ms"]
    assert report["llm_inference_ms"] > 0
    assert report["tool_execution_ms"] > 0


def test_shares_are_a_fraction_of_the_whole():
    report = run_agentic_loop(_fake_model(0.005), DATA_ANALYST_SCRIPT)
    total = report["llm_inference_share"] + report["tool_execution_share"]
    assert 0.0 < total <= 1.0


def test_overhead_is_reported_rather_than_absorbed():
    """If the parts do not add up, the gap must be visible."""
    report = run_agentic_loop(_fake_model(), SWE_AGENT_SCRIPT)
    parts = report["llm_inference_ms"] + report["tool_execution_ms"] + report["overhead_ms"]
    assert parts == pytest.approx(report["end_to_end_ms"], abs=1.0)


def test_a_slow_tool_shows_up_as_tool_time_not_model_time():
    """The distinction the decomposition exists to make."""
    from aihwbench import agentic

    slow_script = (ToolCall(tool="slow_tool"),)
    agentic.TOOLS["slow_tool"] = lambda: time.sleep(0.05) or "done"
    try:
        report = run_agentic_loop(_fake_model(), slow_script)
    finally:
        del agentic.TOOLS["slow_tool"]

    assert report["tool_execution_ms"] > report["llm_inference_ms"]
    assert report["tool_execution_share"] > 0.5


def test_trace_with_no_activity_reports_nothing_rather_than_zero_rates():
    summary = AgenticTrace().summarize()
    assert summary["turns"] == 0
    assert summary["mean_llm_ms_per_turn"] is None
    assert summary["mean_tool_ms_per_call"] is None


def test_the_loop_is_reproducible_across_runs():
    """Same script, same tools, same tool outputs every time."""
    a = run_agentic_loop(_fake_model(), SWE_AGENT_SCRIPT)
    b = run_agentic_loop(_fake_model(), SWE_AGENT_SCRIPT)
    assert a["transcript_chars"] == b["transcript_chars"]
    assert a["tools_used"] == b["tools_used"]


# -------------------------------------------------------------- registration


def test_agentic_workloads_are_registered():
    """The claim in ROADMAP is now backed by a registered workload."""
    from aihwbench.workloads import get_workload, list_workloads

    for workload_id in AGENTIC_SCRIPTS:
        assert workload_id in list_workloads()
        assert get_workload(workload_id).kind == "agentic"


def test_every_registered_agentic_workload_has_a_script():
    from aihwbench.workloads import get_workload, list_workloads

    for workload_id in list_workloads():
        if get_workload(workload_id).kind == "agentic":
            assert workload_id in AGENTIC_SCRIPTS
