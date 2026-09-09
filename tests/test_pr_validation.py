"""The pull-request result validator.

Validation logic embedded in workflow YAML is only ever exercised by opening a
pull request, which is a slow and public way to find out the validator itself
is broken. It lives in a script so these tests can run it.

What blocks a merge is deliberately narrow. A submission that is merely
under-measured, or comparable with nothing yet, is reported and merged:
losing a real measurement from someone whose hardware cannot sit through a
long run is a worse outcome than publishing it with a label.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

validator = importlib.import_module("scripts.validate_pr_results")

PUBLISHED = Path("results/published")


def _write(tmp_path: Path, name: str, **changes) -> Path:
    doc = json.loads((PUBLISHED / "ollama-1787388930.json").read_text(encoding="utf-8"))
    doc["run_id"] = name
    for dotted, value in changes.items():
        section, _, key = dotted.partition(".")
        if key:
            doc.setdefault(section, {})[key] = value
        else:
            doc[section] = value
    path = tmp_path / f"{name}.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def test_a_clean_submission_passes(tmp_path):
    path = _write(tmp_path, "clean")
    assert validator.main([str(path)]) == 0


def test_a_privacy_leak_blocks(tmp_path):
    path = _write(tmp_path, "leaky", **{"system.platform_name": "PC of dev@example.com"})
    assert validator.main([str(path)]) == 1


def test_the_report_never_echoes_the_leaked_value(tmp_path):
    """The comment is public; a finding must not republish the secret."""
    path = _write(tmp_path, "leaky", **{"system.platform_name": "PC of dev@example.com"})
    review = validator.review_result(path)
    report = validator.render([review], [])
    assert "dev@example.com" not in report
    assert "redacted" in report


def test_an_impossible_value_blocks(tmp_path):
    path = _write(tmp_path, "impossible", **{"metrics.peak_vram_mb": 999999})
    assert validator.main([str(path)]) == 1


def test_a_schema_violation_blocks(tmp_path):
    path = _write(tmp_path, "malformed", **{"metrics.generation_tokens_per_second": "fast"})
    assert validator.main([str(path)]) == 1


def test_an_under_measured_run_is_reported_but_does_not_block(tmp_path):
    """A weak number labelled weak beats losing the measurement entirely."""
    path = _write(tmp_path, "single", **{"reproducibility.iterations": 1})
    assert validator.main([str(path)]) == 0
    report = validator.render([validator.review_result(path)], [])
    assert "single_run" in report
    assert "does not" in report and "block" in report


def test_an_unreadable_file_blocks(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")
    assert validator.main([str(path)]) == 1


def test_no_changed_results_is_not_a_failure():
    """A pull request touching only schemas has nothing to validate."""
    assert validator.main([]) == 0


def test_comparability_is_reported_for_a_submission(tmp_path):
    path = _write(tmp_path, "comparable")
    report = validator.render([validator.review_result(path)], sorted(PUBLISHED.glob("*.json")))
    assert "Comparability with the existing dataset" in report


def test_comparable_with_nothing_is_stated_as_normal(tmp_path):
    """New hardware is exactly what 'comparable with nothing' looks like."""
    path = _write(tmp_path, "novel", **{"runtime.name": "some-new-runtime"})
    report = validator.render([validator.review_result(path)], sorted(PUBLISHED.glob("*.json")))
    assert "nothing yet" in report
    assert "not a defect" in report


@pytest.mark.parametrize("path", sorted(PUBLISHED.glob("*.json")))
def test_every_published_result_would_pass_the_gate(path):
    """The dataset must satisfy the bar it holds submissions to."""
    assert validator.main([str(path)]) == 0
