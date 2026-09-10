"""Tests for the CLI (no model downloads, no real inference)."""

import json

from aihwbench.cli import build_parser, main


def test_system_info_command_outputs_json(capsys):
    code = main(["system-info"])
    assert code == 0
    data = json.loads(capsys.readouterr().out)
    assert "cpu" in data
    assert "ram_gb" in data


def test_runtimes_command_lists_backends(capsys):
    code = main(["runtimes"])
    assert code == 0
    out = capsys.readouterr().out
    assert "ollama" in out
    assert "hailo" in out


def test_validate_rejects_bad_file(tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"schema_version": "1.0"}), encoding="utf-8")
    code = main(["validate", str(bad)])
    assert code == 1
    assert "INVALID" in capsys.readouterr().err


def test_benchmark_unknown_runtime_fails_cleanly(capsys):
    # argparse restricts --runtime choices; call run_benchmark path via parser check
    parser = build_parser()
    try:
        parser.parse_args(["benchmark", "--runtime", "bogus", "--model", "x"])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("expected parse failure")


# ------------------------------------------------ regression gate exit codes


def _regression_fixture(tmp_path):
    """A baseline and a candidate that is both much slower and incomparable."""
    from tests.test_ecosystem import _result

    baselines = tmp_path / "baselines"
    baselines.mkdir()
    base = _result("base", 100.0)
    (baselines / "ref.json").write_text(json.dumps(base), encoding="utf-8")

    cand = _result("cand", 1.0)  # 100x slower than baseline
    cand["runtime"]["name"] = "llama.cpp"  # ...and NOT_COMPARABLE
    cand_path = tmp_path / "cand.json"
    cand_path.write_text(json.dumps(cand), encoding="utf-8")
    return baselines, cand_path


def test_regression_gate_does_not_pass_when_incomparable(tmp_path, capsys):
    """The gate must fail closed: zero checks run is not a pass.

    Exit 3 (NOT_COMPARABLE), never 0. `compare` has always done this; the
    regression gate used to return OK here, which made it fail open exactly
    when the runtime, model or hardware had drifted from the baseline.
    """
    baselines, cand = _regression_fixture(tmp_path)
    code = main(["regression", "--baseline", "ref", "--baselines-dir", str(baselines), str(cand)])
    assert code == 3
    assert "NOT_COMPARABLE" in capsys.readouterr().err


def test_regression_gate_force_evaluates_and_still_fails(tmp_path):
    """--force overrides comparability, not the thresholds."""
    baselines, cand = _regression_fixture(tmp_path)
    code = main(
        [
            "regression",
            "--baseline",
            "ref",
            "--baselines-dir",
            str(baselines),
            "--force",
            str(cand),
        ]
    )
    assert code == 5  # EXIT_REGRESSION_DETECTED


def test_quantization_refuses_a_speed_only_table(tmp_path, capsys):
    """The anti-goal: speed across quantizations with no quality signal.

    Lower precision is faster and also changes the output. Publishing the
    first without the second walks a reader into a worse configuration while
    looking like measured data.
    """
    from tests.test_ecosystem import _result

    published = tmp_path / "published"
    published.mkdir()
    doc = _result("speed-only", 90.0)
    doc["model"]["quantization"] = "q4_0"
    doc.pop("quality", None)
    (published / "a.json").write_text(json.dumps(doc), encoding="utf-8")

    code = main(["quantization", "--results-dir", str(published)])
    assert code == 1
    assert "speed-only quantization table" in capsys.readouterr().err


def test_quantization_prints_when_a_quality_signal_is_present(tmp_path, capsys):
    from tests.test_ecosystem import _result

    published = tmp_path / "published"
    published.mkdir()
    doc = _result("with-quality", 90.0)
    doc["model"]["quantization"] = "q4_0"
    doc["quality"] = {"output_hash": "sha256:abc", "deterministic": True}
    (published / "a.json").write_text(json.dumps(doc), encoding="utf-8")

    assert main(["quantization", "--results-dir", str(published)]) == 0
    assert "output_hash" in capsys.readouterr().out


def test_quantization_override_is_available_but_explicit(tmp_path):
    from tests.test_ecosystem import _result

    published = tmp_path / "published"
    published.mkdir()
    doc = _result("speed-only", 90.0)
    doc["model"]["quantization"] = "q4_0"
    doc.pop("quality", None)
    (published / "a.json").write_text(json.dumps(doc), encoding="utf-8")

    assert (
        main(
            [
                "quantization",
                "--results-dir",
                str(published),
                "--allow-missing-quality",
            ]
        )
        == 0
    )


# --- Conformance report ------------------------------------------------------
#
# `doctor` printed a report only a human could read, so someone on hardware
# the maintainers cannot test had no structured way to say what their machine
# reaches. A second module (`backends/capabilities.py`) existed to build such a
# report and was never called by anything; two sources of truth about backend
# availability, able to disagree, is worse than one.


def test_doctor_json_is_a_structured_conformance_report(capsys):
    code = main(["doctor", "--json"])
    assert code in (0, 4)  # 4 when this machine has a detection problem
    report = json.loads(capsys.readouterr().out)

    assert report["kind"] == "conformance-report"
    assert "system" in report and "cpu" in report["system"]
    assert report["runtimes"], "expected at least one backend"
    for runtime in report["runtimes"]:
        assert "name" in runtime
        assert "status" in runtime
    assert isinstance(report["problems"], list)


def test_doctor_json_reports_no_measurements(capsys):
    """It is pasted into public issues, so it must carry no performance claim."""
    main(["doctor", "--json"])
    report = json.loads(capsys.readouterr().out)

    assert "no benchmark was executed" in report["note"]
    serialized = json.dumps(report)
    for metric in ("tokens_per_second", "latency_ms", "power_watts"):
        assert metric not in serialized


def test_doctor_text_and_json_agree_on_backends(capsys):
    """One source of truth: the JSON view must not drift from the printed one."""
    main(["doctor", "--json"])
    report = json.loads(capsys.readouterr().out)
    main(["doctor"])
    text = capsys.readouterr().out

    for runtime in report["runtimes"]:
        assert runtime["name"] in text


# --- Snapshot diffing --------------------------------------------------------
#
# `diff_snapshots` existed and nothing called it, while
# `build_snapshot_manifest` computed the same set arithmetic inline -- two
# implementations of "what changed between two snapshots", free to disagree.
# There is one now, and it is reachable from the CLI for the case the builder
# cannot serve: comparing two manifests when the directories they described
# are long gone.


def _manifest(tmp_path, name, members, version):
    import json as _json

    path = tmp_path / name
    path.write_text(_json.dumps({"version": version, "members": members}), encoding="utf-8")
    return str(path)


def test_snapshot_diff_reports_added_and_removed(tmp_path, capsys):
    old = _manifest(tmp_path, "old.json", {"a.json": "h1", "b.json": "h2"}, "v1")
    new = _manifest(tmp_path, "new.json", {"b.json": "h2", "c.json": "h3"}, "v2")

    assert main(["snapshot", "--diff", old, new]) == 0
    diff = json.loads(capsys.readouterr().out)
    assert diff["added"] == ["c.json"]
    assert diff["removed"] == ["a.json"]
    assert diff["changed"] == []
    assert diff["old_version"] == "v1"
    assert diff["new_version"] == "v2"


def test_snapshot_diff_catches_a_result_edited_in_place(tmp_path, capsys):
    """The case worth catching: same filename, different content.

    A published result quietly edited after people cited it keeps its name, so
    only the content hash reveals it.
    """
    old = _manifest(tmp_path, "old.json", {"a.json": "h1"}, "v1")
    new = _manifest(tmp_path, "new.json", {"a.json": "DIFFERENT"}, "v2")

    assert main(["snapshot", "--diff", old, new]) == 0
    diff = json.loads(capsys.readouterr().out)
    assert diff["changed"] == ["a.json"]
    assert diff["added"] == [] and diff["removed"] == []


def test_snapshot_diff_rejects_a_missing_manifest(tmp_path, capsys):
    old = _manifest(tmp_path, "old.json", {}, "v1")
    code = main(["snapshot", "--diff", old, str(tmp_path / "absent.json")])
    assert code == 2
    assert "not a file" in capsys.readouterr().err


def test_snapshot_requires_a_version_when_building(capsys):
    assert main(["snapshot"]) == 2
    assert "--version is required" in capsys.readouterr().err


def test_manifest_changes_agree_with_the_differ(tmp_path):
    """The builder's inline changes and the differ must not drift apart."""
    from aihwbench.dataset_versioning import build_snapshot_manifest, diff_snapshots

    results = tmp_path / "published"
    results.mkdir()
    (results / "one.json").write_text(json.dumps({"run_id": "one"}), encoding="utf-8")
    first = build_snapshot_manifest(results, "v1")

    (results / "two.json").write_text(json.dumps({"run_id": "two"}), encoding="utf-8")
    (results / "one.json").write_text(json.dumps({"run_id": "one!"}), encoding="utf-8")
    second = build_snapshot_manifest(results, "v2", first)

    standalone = diff_snapshots(first, second)
    for key in ("added", "removed", "changed"):
        assert second["changes_vs_previous"][key] == standalone[key]
    assert standalone["added"] == ["two.json"]
    assert standalone["changed"] == ["one.json"]


# --- `--output` semantics -----------------------------------------------------
#
# Some commands take a directory and some take a file path, and passing a file
# path where a directory is expected silently creates a folder with that name:
# `aihwbench tune --output tune.json` produces a directory called `tune.json`
# and reports success. Seven of these flags carried no help text at all, so
# there was no way to know which kind a command wanted short of reading the
# source.


def test_every_output_flag_says_whether_it_wants_a_file_or_a_directory():
    from aihwbench.cli import build_parser

    parser = build_parser()
    subparsers = [
        action for action in parser._actions if hasattr(action, "choices") and action.choices
    ]
    assert subparsers, "expected the CLI to have subcommands"

    undocumented = []
    for action in subparsers:
        for name, sub in action.choices.items():
            for arg in sub._actions:
                if "--output" not in getattr(arg, "option_strings", []):
                    continue
                help_text = (arg.help or "").lower()
                if not any(word in help_text for word in ("director", "file", "path", "bundle")):
                    undocumented.append(name)
    assert not undocumented, (
        "these commands' --output does not say whether it takes a file or a "
        f"directory: {sorted(set(undocumented))}"
    )


# --- Length-only workloads are runnable, and their context fits --------------
#
# Thirteen of seventeen registered workloads could not be run by `benchmark`,
# because they declare an input length rather than carrying a prompt — while
# `synthesize_prompt`, which turns a length into a deterministic prompt, sat in
# `workloads/builtin.py` with no callers.
#
# Enabling them exposed the next problem: `long_prompt` declares 4096 input
# tokens and ran at the 2048-token default context, so the server truncated a
# 3331-token prompt to 1026 and reported prefill throughput for a third of the
# intended input. `workload.isl_tokens` said 4096, `metrics.prompt_tokens` said
# 1026, and the two never met.


def test_length_only_workloads_are_offered():
    from aihwbench.cli import build_parser

    parser = build_parser()
    action = next(
        a
        for sub in parser._actions
        if getattr(sub, "choices", None) and "benchmark" in (sub.choices or {})
        for a in sub.choices["benchmark"]._actions
        if "--workload" in getattr(a, "option_strings", [])
    )
    offered = set(action.choices or [])
    for length_profile in ("long_prompt", "prefill_only", "decode_only", "long_context"):
        assert length_profile in offered, f"{length_profile} is registered but unrunnable"


def test_multi_request_workloads_are_not_offered():
    """Running `multi_turn_8` as one request measures a single turn.

    Offering it here would let someone believe they measured eight.
    """
    from aihwbench.cli import build_parser

    parser = build_parser()
    action = next(
        a
        for sub in parser._actions
        if getattr(sub, "choices", None) and "benchmark" in (sub.choices or {})
        for a in sub.choices["benchmark"]._actions
        if "--workload" in getattr(a, "option_strings", [])
    )
    offered = set(action.choices or [])
    for driven_elsewhere in ("multi_turn_8", "mixed_traffic_realistic", "agentic_swe"):
        assert driven_elsewhere not in offered


def test_a_synthesized_prompt_is_deterministic():
    """Two machines running `long_prompt` must send the same bytes.

    Otherwise the profile is not a comparable measurement — it is two people
    each inventing 4096 tokens of their own.
    """
    from aihwbench.workloads.builtin import synthesize_prompt

    assert synthesize_prompt(512) == synthesize_prompt(512)
    assert synthesize_prompt(512) != synthesize_prompt(1024)


def test_the_context_is_raised_to_hold_the_workload():
    from aihwbench.cli import build_parser

    parser = build_parser()
    args = parser.parse_args(
        ["benchmark", "--runtime", "ollama", "--model", "m", "--workload", "long_prompt"]
    )
    # The parser leaves the default in place; cmd_benchmark raises it. Check
    # the default it must raise *from*, so a changed default is caught here.
    from aihwbench.cli.benchmark import _DEFAULT_CONTEXT_LENGTH
    from aihwbench.workloads import get_workload

    assert args.context_length == _DEFAULT_CONTEXT_LENGTH
    workload = get_workload("long_prompt")
    needed = (workload.isl_tokens or 0) + (workload.osl_tokens or 0)
    assert needed > _DEFAULT_CONTEXT_LENGTH, (
        "long_prompt no longer exceeds the default context, so this test no "
        "longer covers the truncation it was written for"
    )


def test_an_explicit_context_length_is_not_overridden():
    """A caller who set it meant it, even if the workload wants more."""
    from aihwbench.cli import build_parser

    parser = build_parser()
    args = parser.parse_args(
        [
            "benchmark",
            "--runtime",
            "ollama",
            "--model",
            "m",
            "--workload",
            "long_prompt",
            "--context-length",
            "1024",
        ]
    )
    assert args.context_length == 1024
