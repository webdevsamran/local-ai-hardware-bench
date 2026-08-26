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
