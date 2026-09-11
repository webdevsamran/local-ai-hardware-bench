"""Speculative decoding is sold as a free 2x; the acceptance rate decides.

Each verification step costs one target forward pass however many draft tokens
it checks, plus the draft model's own passes. High acceptance means several
tokens per target pass and a real speedup. Low acceptance means paying for a
draft model and discarding its output, and speculative decoding *loses* — with
no symptom except that the promised speedup did not arrive.

Almost nobody publishes the rate, which is why the plan marks it as a
differentiator.

The state this is built around
------------------------------

Measured on the reference machine: llama.cpp loaded the draft model, logged
`common_speculative_init_result: loading draft model`, raised no warning,
served requests normally, and left every speculative counter at zero.
Speculation never ran.

"Acceptance rate 0%" would send someone looking for a better draft model.
"Speculation did not engage" sends them to their runtime configuration, which
is where the fault is. The two states must not be collapsed.
"""

from __future__ import annotations

from aihwbench.analysis.speculative import (
    SPECULATIVE_METRICS,
    acceptance_report,
    net_speedup,
    parse_speculative_metrics,
)

#: A real `/metrics` scrape from the reference machine, speculation not engaged.
REAL_SCRAPE_NOT_ENGAGED = """# HELP llamacpp:spec_decode_num_draft_tokens_total Speculative: Total draft tokens generated
# TYPE llamacpp:spec_decode_num_draft_tokens_total counter
llamacpp:spec_decode_num_draft_tokens_total 0
# TYPE llamacpp:spec_decode_num_accepted_tokens_total counter
llamacpp:spec_decode_num_accepted_tokens_total 0
# TYPE llamacpp:spec_decode_num_drafts_total counter
llamacpp:spec_decode_num_drafts_total 0
"""

ENGAGED_SCRAPE = """llamacpp:spec_decode_num_draft_tokens_total 800
llamacpp:spec_decode_num_accepted_tokens_total 520
llamacpp:spec_decode_num_drafts_total 130
"""

ZEROES = dict.fromkeys(SPECULATIVE_METRICS, 0.0)


def test_it_reads_the_counters_llama_server_actually_exposes():
    parsed = parse_speculative_metrics(REAL_SCRAPE_NOT_ENGAGED)
    assert parsed == {"draft_tokens": 0.0, "accepted_tokens": 0.0, "drafts": 0.0}


def test_a_runtime_that_exposes_no_counters_is_unknown_not_zero():
    """Absent counters have not told us there were no drafts."""
    parsed = parse_speculative_metrics("llamacpp:tokens_predicted_total 42\n")
    assert all(value is None for value in parsed.values())
    report = acceptance_report(parsed, parsed)
    assert report["speculation_engaged"] is None
    assert "--metrics" in report["unresolved"]


def test_no_drafts_is_reported_as_not_engaged_rather_than_zero_acceptance():
    """The distinction this module exists for.

    Zero acceptance means the draft model was consulted and always wrong.
    Nothing was consulted here, and the two send a reader to different places.
    """
    report = acceptance_report(ZEROES, parse_speculative_metrics(REAL_SCRAPE_NOT_ENGAGED))
    assert report["speculation_engaged"] is False
    assert report["acceptance_rate"] is None
    assert "not an acceptance rate of zero" in report["unresolved"]


def test_an_engaged_run_reports_the_rate_and_the_tokens_per_verification():
    report = acceptance_report(ZEROES, parse_speculative_metrics(ENGAGED_SCRAPE))
    assert report["speculation_engaged"] is True
    assert report["acceptance_rate"] == 0.65
    # 520 accepted over 130 verification steps: four tokens per target pass.
    assert report["accepted_per_verification"] == 4.0


def test_counters_are_differenced_because_they_are_cumulative():
    """A report from the final scrape alone averages in every earlier request.

    On a long-lived server that is most of them, and the run being measured
    disappears into the mean.
    """
    before = {"draft_tokens": 800.0, "accepted_tokens": 520.0, "drafts": 130.0}
    after = {"draft_tokens": 900.0, "accepted_tokens": 540.0, "drafts": 150.0}
    report = acceptance_report(before, after)
    assert report["draft_tokens"] == 100
    assert report["accepted_tokens"] == 20
    assert report["acceptance_rate"] == 0.2


def test_the_rate_carries_the_workload_because_it_does_not_transfer():
    """Code drafts well and open prose drafts badly.

    A rate published without the workload beside it invites being applied to a
    different one.
    """
    report = acceptance_report(ZEROES, parse_speculative_metrics(ENGAGED_SCRAPE), "code_completion")
    assert report["workload"] == "code_completion"
    assert "does not transfer" in report["caveat"]


# --- did it actually pay? ---------------------------------------------------


def test_a_real_speedup_is_reported_with_its_memory_cost():
    """A speedup bought with memory you do not have is not a speedup."""
    report = net_speedup(
        {"generation_tokens_per_second": 150.0, "peak_vram_mb": 1400.0},
        {"generation_tokens_per_second": 100.0, "peak_vram_mb": 1000.0},
    )
    assert report["speedup"] == 1.5
    assert report["helped"] is True
    assert report["draft_memory_overhead_mb"] == 400.0


def test_a_slowdown_is_reported_as_one_rather_than_floored():
    """ "Speculative decoding made this slower" is the finding someone needs
    before shipping it, and it is a common outcome."""
    report = net_speedup(
        {"generation_tokens_per_second": 80.0},
        {"generation_tokens_per_second": 100.0},
    )
    assert report["speedup"] == 0.8
    assert report["helped"] is False
    assert "SLOWER" in report["caveat"]


def test_comparing_a_run_that_never_speculated_says_so():
    """Otherwise the ratio looks like a speculative result and is noise."""
    not_engaged = acceptance_report(ZEROES, parse_speculative_metrics(REAL_SCRAPE_NOT_ENGAGED))
    report = net_speedup(
        {"generation_tokens_per_second": 101.0},
        {"generation_tokens_per_second": 100.0},
        not_engaged,
    )
    assert "did not engage" in report["caveat"]


def test_a_missing_rate_cannot_be_compared():
    assert net_speedup({}, {})["speedup"] is None
    assert net_speedup({"generation_tokens_per_second": 10.0}, {})["speedup"] is None


# --- reachable from a sweep -------------------------------------------------


def test_the_backend_declares_the_draft_axes():
    from aihwbench.backends.llama_cpp import TUNABLE_AXES

    for axis in (
        "draft_model",
        "draft_n_max",
        "draft_n_min",
        "draft_p_min",
        "draft_gpu_layers",
        "cache_type_k_draft",
        "cache_type_v_draft",
    ):
        assert axis in TUNABLE_AXES


def test_the_draft_flags_reach_the_command_line():
    import inspect

    from aihwbench.backends import llama_cpp

    source = inspect.getsource(llama_cpp.LlamaServerHandle.__enter__)
    for flag in ("--model-draft", "--spec-draft-n-max", "--cache-type-", "--metrics"):
        assert flag in source


def test_an_unknown_draft_cache_type_is_refused():
    """Asymmetric main/draft KV is a real configuration; a typo in it is not."""
    import pytest

    from aihwbench.backends.base import BackendError, BenchmarkConfig
    from aihwbench.backends.llama_cpp import LlamaServerHandle

    handle = LlamaServerHandle(
        "llama-server",
        "model.gguf",
        BenchmarkConfig(
            model="m",
            extra={"draft_model": "d.gguf", "cache_type_k_draft": "q3_k_m"},
        ),
    )
    with pytest.raises(BackendError, match="unknown draft KV cache type"):
        handle.__enter__()
