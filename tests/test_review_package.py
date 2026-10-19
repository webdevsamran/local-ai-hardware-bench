"""Tests for full 54-metric detailed reports and multi-model review packages."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from aihwbench.cli import main
from aihwbench.exporters import get_exporter, list_exporters
from aihwbench.metrics import METRIC_DESCRIPTIONS, METRIC_REGISTRY
from aihwbench.report import render_detailed_report, render_report
from aihwbench.review_package import (
    build_review_package,
    render_executive_summary_html,
    render_executive_summary_markdown,
)
from tests.test_schemas import make_valid_result


def _sample_result(run_id: str = "run-001", model_name: str = "qwen2.5:0.5b") -> dict:
    doc = make_valid_result()
    doc["run_id"] = run_id
    doc["model"]["name"] = model_name
    doc["metrics"]["generation_tokens_per_second"] = 125.4
    doc["metrics"]["prompt_tokens_per_second"] = 1850.0
    doc["metrics"]["ttft_ms"] = 18.5
    doc["metrics"]["average_power_watts"] = 85.0
    doc["metrics"]["tokens_per_second_per_watt"] = 1.475
    return doc


def test_metric_descriptions_cover_all_registry_metrics() -> None:
    assert set(METRIC_DESCRIPTIONS.keys()) == set(METRIC_REGISTRY.keys())
    for key, desc in METRIC_DESCRIPTIONS.items():
        assert isinstance(desc, str) and len(desc) > 5, f"empty description for {key}"


def test_render_detailed_report_lists_all_54_canonical_metrics() -> None:
    doc = _sample_result()
    md = render_detailed_report(doc)
    assert len(METRIC_REGISTRY) == 54
    for metric_key in METRIC_REGISTRY:
        assert f"`{metric_key}`" in md, f"detailed report missing canonical metric {metric_key}"
    assert "not measured" in md
    assert "## 3. Complete Metric Specification (All 54 Repository Metrics)" in md


def test_render_report_full_flag_delegates_to_detailed_report() -> None:
    doc = _sample_result()
    compact = render_report(doc, full=False)
    detailed = render_report(doc, full=True)
    assert "# Benchmark Report" in compact
    assert "Complete Metric Specification (All 54 Repository Metrics)" in detailed
    for metric_key in METRIC_REGISTRY:
        assert f"`{metric_key}`" in detailed


def test_executive_summary_markdown_and_html() -> None:
    results = [
        _sample_result("run-001", "model-alpha"),
        _sample_result("run-002", "model-beta"),
    ]
    md = render_executive_summary_markdown(
        results,
        title="Test Evaluation Report",
        subtitle="Unit Test Subtitle",
        prepared_for="Engineering Review",
        confidential=True,
    )
    assert "# Test Evaluation Report" in md
    assert "CONFIDENTIAL PRE-PUBLICATION REVIEW" in md
    assert "model-alpha" in md
    assert "model-beta" in md
    for metric_key in METRIC_REGISTRY:
        assert f"`{metric_key}`" in md

    html_doc = render_executive_summary_html(
        results,
        title="Test Evaluation Report",
        subtitle="Unit Test Subtitle",
        prepared_for="Engineering Review",
        confidential=True,
    )
    assert "<!DOCTYPE html>" in html_doc
    assert "Test Evaluation Report" in html_doc
    assert "model-alpha" in html_doc
    assert "model-beta" in html_doc
    for metric_key in METRIC_REGISTRY:
        assert metric_key in html_doc


def test_html_exporter_is_registered_and_exports(tmp_path: Path) -> None:
    assert "html" in list_exporters()
    out_file = tmp_path / "summary.html"
    exporter = get_exporter("html")
    written = exporter.export([_sample_result()], out_file)
    assert written == out_file
    content = out_file.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in content
    assert "qwen2.5:0.5b" in content


def test_build_review_package_creates_bundle_and_zip(tmp_path: Path, monkeypatch) -> None:
    # Avoid invoking headless browser subprocess during unit test
    monkeypatch.setattr("aihwbench.review_package.compile_html_to_pdf", lambda h, p: None)

    src_dir = tmp_path / "inputs"
    src_dir.mkdir(parents=True, exist_ok=True)
    for idx, name in enumerate(("model-one", "model-two"), start=1):
        doc = _sample_result(f"run-00{idx}", name)
        (src_dir / f"run-00{idx}.json").write_text(json.dumps(doc), encoding="utf-8")

    out_dir = tmp_path / "pkg"
    zip_file = tmp_path / "pkg.zip"
    manifest = build_review_package(
        src_dir,
        out_dir,
        zip_path=zip_file,
        title="Package Test",
        confidential=True,
    )

    assert manifest["model_count"] == 2
    assert (out_dir / "00_Executive_Summary_All_Models.md").is_file()
    assert (out_dir / "00_Executive_Summary_All_Models.html").is_file()
    assert len(list((out_dir / "models").glob("*.md"))) == 2
    assert len(list((out_dir / "raw_results").glob("*.json"))) == 2
    assert zip_file.is_file()

    with zipfile.ZipFile(zip_file, "r") as zf:
        names = set(zf.namelist())
        assert "00_Executive_Summary_All_Models.md" in names
        assert "00_Executive_Summary_All_Models.html" in names
        assert any(n.startswith("models/") and n.endswith(".md") for n in names)
        assert any(n.startswith("raw_results/") and n.endswith(".json") for n in names)


def test_cli_report_full_and_review_package(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("aihwbench.review_package.compile_html_to_pdf", lambda h, p: None)

    src_dir = tmp_path / "results"
    src_dir.mkdir(parents=True, exist_ok=True)
    doc_path = src_dir / "sample.json"
    doc_path.write_text(json.dumps(_sample_result()), encoding="utf-8")

    full_md = tmp_path / "full.md"
    assert main(["report", str(doc_path), "--full", "--output", str(full_md)]) == 0
    assert full_md.is_file()
    assert "`generation_tokens_per_second`" in full_md.read_text(encoding="utf-8")

    html_out = tmp_path / "report.html"
    assert main(["report", str(doc_path), "--format", "html", "--output", str(html_out)]) == 0
    assert html_out.is_file()
    assert "<!DOCTYPE html>" in html_out.read_text(encoding="utf-8")

    pkg_dir = tmp_path / "review_out"
    zip_out = tmp_path / "review_out.zip"
    code = main(
        [
            "review-package",
            "--results-dir",
            str(src_dir),
            "--output",
            str(pkg_dir),
            "--zip",
            str(zip_out),
            "--confidential",
        ]
    )
    assert code == 0
    assert (pkg_dir / "00_Executive_Summary_All_Models.md").is_file()
    assert zip_out.is_file()
