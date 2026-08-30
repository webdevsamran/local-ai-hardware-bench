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
