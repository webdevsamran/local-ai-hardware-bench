"""Tests for CI gate fail-closed behavior — Fix 12.

The reusable benchmark-validation workflow must fail closed when configured
and must never swallow errors with ``|| true``; the release workflow's SBOM
is a mandatory security artifact (no "skipped" fallback); the regression
candidate is selected deterministically (never ``ls | head``).
"""

from __future__ import annotations

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml", reason="pyyaml not installed")

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"


def _load(name: str) -> dict:
    doc = yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))
    assert isinstance(doc, dict)
    return doc


def _steps(doc: dict) -> list[dict]:
    return [
        step
        for job in doc.get("jobs", {}).values()
        for step in job.get("steps", [])
        if isinstance(step, dict)
    ]


def _all_step_texts(doc: dict) -> list[str]:
    return [str(s.get("run", "")) + str(s.get("name", "")) for s in _steps(doc)]


# ---------------------------------------------------------------------------
# benchmark-validation.yml
# ---------------------------------------------------------------------------


def test_benchmark_validation_parses_and_fails_closed():
    doc = _load("benchmark-validation.yml")
    steps = _steps(doc)
    names = [s.get("name", "") for s in steps]
    assert names.count("Fail closed on validation verdict") == 1
    assert names.count("Select newest candidate (deterministic)") == 1

    fail_step = next(s for s in steps if s.get("name") == "Fail closed on validation verdict")
    assert "exit 1" in str(fail_step.get("run", ""))
    # The gate is driven by the aggregated verdict output, not a swallow.
    assert "steps.validate.outputs.verdict" in str(fail_step.get("if", ""))


def test_no_error_swallowing_in_validate_loop():
    doc = _load("benchmark-validation.yml")
    texts = "\n".join(_all_step_texts(doc))
    # `|| true` / `|| echo "skipped"` would silently hide failures.
    assert "|| true" not in texts
    assert "|| \\" not in texts
    # The validate loop captures per-file quality reports and flips verdict
    # on non-zero exit instead of ignoring it.
    assert "if ! aihwbench validate" in texts
    assert 'verdict="fail"' in texts


def test_regression_candidate_is_deterministic():
    doc = _load("benchmark-validation.yml")
    texts = "\n".join(_all_step_texts(doc))
    assert 'ls "${{ inputs.results-dir }}"/*.json | head' not in texts
    assert "max(files, key=ts)" in texts  # newest timestamp selection


# ---------------------------------------------------------------------------
# release.yml — SBOM is mandatory
# ---------------------------------------------------------------------------


def test_release_sbom_is_mandatory_and_verified():
    doc = _load("release.yml")
    names = [s.get("name", "") for s in _steps(doc)]
    assert "Generate SBOM (CycloneDX)" in names
    assert names.count("Verify SBOM was generated and is valid") == 1
    texts = "\n".join(_all_step_texts(doc))
    assert "SBOM generation skipped" not in texts
    assert "cyclonedx-py requirements --output-format json" in texts
    assert 'assert sbom.get("bomFormat") == "CycloneDX"' in texts


# ---------------------------------------------------------------------------
# All workflows parse
# ---------------------------------------------------------------------------


def test_all_workflows_parse():
    for p in sorted(WORKFLOWS.glob("*.yml")):
        yaml.safe_load(p.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# .github/actions/run-benchmark — the contributor-hardware action
# ---------------------------------------------------------------------------
#
# This action runs on machines the maintainers will never see, so a mistake in
# it surfaces as a stranger's failed job. The tests below check the two things
# that can be checked here: that every CLI invocation matches the real parser,
# and that the action cannot quietly do the things it promises not to do.

ACTION = ROOT / ".github" / "actions" / "run-benchmark" / "action.yml"


def _action() -> dict:
    doc = yaml.safe_load(ACTION.read_text(encoding="utf-8"))
    assert isinstance(doc, dict)
    return doc


def _action_run_text() -> str:
    return "\n".join(str(step.get("run", "")) for step in _action()["runs"]["steps"])


def test_run_benchmark_action_is_a_valid_composite_action():
    doc = _action()
    assert doc["runs"]["using"] == "composite"
    assert doc["inputs"]["runtime"]["required"] is True
    # Every composite `run` step must declare a shell, or the action fails to
    # load at all -- and only on the contributor's runner.
    for step in doc["runs"]["steps"]:
        if "run" in step:
            assert step.get("shell"), f"step {step.get('name')!r} has no shell"


def test_action_cli_flags_exist_in_the_real_parser():
    """A renamed flag must fail here, not on a stranger's machine.

    The action is text; nothing else checks that `--formal`, `--workload` or
    `doctor --json` are still real. Parsing the exact invocations against the
    live parser is what turns that text back into something verified.
    """
    from aihwbench.cli import build_parser

    parser = build_parser()
    invocations = [
        ["doctor", "--json"],
        ["validate", "some-result.json", "--formal"],
        ["quality", "some-result.json"],
        ["redact", "some-result.json", "--output", "out.json"],
        [
            "benchmark",
            "--runtime",
            "ollama",
            "--model",
            "m",
            "--workload",
            "sustained_generation",
            "--iterations",
            "8",
            "--warmup",
            "3",
            "--output",
            "benchmark-output",
        ],
    ]
    for argv in invocations:
        parser.parse_args(argv)  # raises SystemExit if a flag is wrong

    # And each of those commands really appears in the action.
    text = _action_run_text()
    for command in ("doctor --json", "--formal", "aihwbench quality", "aihwbench redact"):
        assert command in text, f"action no longer runs: {command}"


def test_action_refuses_shared_runners_by_default():
    """A shared VM has no power telemetry and no stable thermal behaviour.

    Measuring one produces a plausible number that describes the datacentre's
    scheduling rather than any hardware, which is worse than measuring
    nothing.
    """
    doc = _action()
    guard = doc["runs"]["steps"][0]
    assert "Refuse" in guard["name"]
    assert "github-hosted" in guard["run"]
    assert doc["inputs"]["allow-hosted-runner"]["default"] == "false"
    # The guard runs before anything is installed or measured.
    assert doc["runs"]["steps"].index(guard) == 0


def test_action_never_publishes_or_opens_a_pull_request():
    """Publishing sets a trust state, and a machine cannot review itself."""
    text = ACTION.read_text(encoding="utf-8")
    lowered = text.lower()
    for forbidden in ("git push", "git commit", "gh pr create", "peter-evans/create-pull-request"):
        assert forbidden not in lowered, f"action must not {forbidden}"
    # `results/published` may only be mentioned as instructions to a human.
    assert "--output benchmark-output" in text


def test_action_scans_for_private_data_before_uploading():
    """The upload is what would publish a leak, so the scan must precede it."""
    steps = _action()["runs"]["steps"]
    names = [s.get("name") or s.get("uses", "") for s in steps]
    scan = next(i for i, n in enumerate(names) if "private" in n.lower())
    upload = next(i for i, n in enumerate(names) if "upload" in n.lower())
    assert scan < upload


def test_action_defaults_to_a_workload_that_can_measure_a_rate():
    """The default chat prompt stops after ~29 tokens, measuring clock ramp."""
    doc = _action()
    assert doc["inputs"]["workload"]["default"] == "sustained_generation"
    assert int(doc["inputs"]["iterations"]["default"]) >= 5
