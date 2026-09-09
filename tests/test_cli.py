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
