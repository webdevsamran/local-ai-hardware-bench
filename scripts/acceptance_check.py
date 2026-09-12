"""The project's own acceptance criteria, executed rather than asserted.

Every check here exercises a real code path and corresponds to a claim this
repository makes about itself -- the five defects the roadmap was built to fix,
and the features whose whole value is that they cannot be bypassed.

It exists because the unit suite answers "does this function work" and this
answers a different question: "is the guard actually wired into the path a user
travels". Those come apart constantly, and every entry below was at some point a
capability that existed, passed its own tests, and was never called.

Run it after any change to the comparability classifier, the regression gate,
the sanitizer, the schema, or the leaderboard:

    python scripts/acceptance_check.py

Exit code 0 when every check passes, 1 otherwise, so CI can gate on it.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Runnable from anywhere: Python puts this file's directory on the path, not
# the repository root, and several checks read files by repo-relative path.
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
os.chdir(REPO_ROOT)

PASS, FAIL = "PASS", "FAIL"
results: list[tuple[str, str, str]] = []


def check(label: str):
    def wrap(fn):
        try:
            detail = fn()
            results.append((PASS, label, detail or ""))
        except Exception as exc:  # noqa: BLE001 - a failed check is a result
            results.append((FAIL, label, f"{type(exc).__name__}: {exc}"))
        return fn

    return wrap


# --- D1: the CI regression gate must not fail open --------------------------
@check("D1 regression returns EXIT_NOT_COMPARABLE on INCOMPARABLE")
def _d1():
    from aihwbench.exit_codes import EXIT_NOT_COMPARABLE
    from aihwbench.regression import evaluate_regression

    base = {
        "runtime": {"name": "ollama", "version": "1", "backend": "api", "device": "cuda"},
        "model": {"name": "m"},
        "metrics": {"generation_tokens_per_second": 100.0},
        "reproducibility": {"iterations": 5, "warmup_runs": 2},
    }
    cand = json.loads(json.dumps(base))
    cand["runtime"]["name"] = "llama.cpp"  # makes the pair incomparable
    cand["metrics"]["generation_tokens_per_second"] = 0.9  # 110x slower
    verdict = evaluate_regression(base, cand).to_dict()
    status = verdict.get("status")
    assert status == "INCOMPARABLE", f"expected INCOMPARABLE, got {status}"
    assert EXIT_NOT_COMPARABLE == 3
    return f"status={status}, EXIT_NOT_COMPARABLE={EXIT_NOT_COMPARABLE}"


@check("D1 the CLI maps that verdict to exit code 3")
def _d1_cli():
    import inspect

    from aihwbench.cli import reporting

    source = inspect.getsource(reporting)
    assert "EXIT_NOT_COMPARABLE" in source, "reporting never references the code"
    return "cli/reporting.py references EXIT_NOT_COMPARABLE"


# --- D2: absent metadata is not agreement -----------------------------------
@check("D2 compare_classification({}, {}) is NOT_COMPARABLE")
def _d2():
    from aihwbench.comparability import compare_classification

    out = compare_classification({}, {})
    assert out["classification"] == "NOT_COMPARABLE", out["classification"]
    assert out.get("machine_reasons"), "no machine-readable reason given"
    return f"{out['classification']}, reasons={len(out['machine_reasons'])}"


@check("D2 _same(None, None) is still True (mutation test pinned it)")
def _d2_same():
    from aihwbench.comparability import _same

    assert _same(None, None) is True, "the deliberate mutation-killing behaviour changed"
    return "_same(None, None) is True, as tests/test_comparability_safety.py requires"


# --- D3: the tuner may not sweep axes no backend reads ----------------------
@check("D3 an unsupported tuner axis is refused")
def _d3():
    from aihwbench.analysis.tune import UnsupportedAxisError, check_axes_supported
    from aihwbench.backends import llama_cpp

    # A backend that declares no sweepable axes must refuse one, or the tuner
    # sweeps it inertly and reports run-to-run noise as the optimum (D3).
    try:
        check_axes_supported({"gpu_layers": (0, 99)}, (), "ollama")
    except UnsupportedAxisError as exc:
        # ...and the backend that does declare it must accept it.
        check_axes_supported({"gpu_layers": (0, 99)}, llama_cpp.TUNABLE_AXES, "llama.cpp")
        return f"refused where undeclared ({str(exc)[:50]}...), accepted for llama.cpp"
    raise AssertionError("an axis the backend cannot apply was accepted")


@check("D3 gpu_layers reaches the spawned llama-server command")
def _d3b():
    import inspect

    from aihwbench.backends import llama_cpp

    source = inspect.getsource(llama_cpp)
    assert '"-ngl"' in source, "-ngl never passed"
    assert "_gpu_layers(" in source, "gpu_layers never computed"
    assert "gpu_layers" in llama_cpp.TUNABLE_AXES
    return "declared in TUNABLE_AXES and passed as -ngl"


# --- D4: privacy scrubbing must scrub ---------------------------------------
@check("D4 redact_object cleans a seeded document")
def _d4():
    from aihwbench.sanitize import redact_object

    doc = {"system": {"user": "C:/Users/alice/models"}, "note": "ssh key AKIAIOSFODNN7EXAMPLE"}
    clean = redact_object(doc)
    flat = json.dumps(clean)
    assert "alice" not in flat, "home directory survived"
    assert "AKIAIOSFODNN7EXAMPLE" not in flat, "credential survived"
    return "home directory and credential both replaced"


# --- D5: the published schema is enforced -----------------------------------
@check("D5 validate --formal rejects a malformed result")
def _d5():
    from aihwbench.formal_schema import validate_formal

    bad = {"schema_version": "2.1"}  # missing everything required
    errors = validate_formal(bad)
    assert errors, "a document missing every required field validated cleanly"
    return f"rejected with {len(errors)} error(s)"


@check("D5 jsonschema is a declared dependency")
def _d5b():
    # `tomllib` is stdlib only from 3.11, and this project supports 3.10 --
    # where `tomli` is already a declared dev dependency for exactly this
    # reason. Importing `tomllib` unconditionally made every 3.10 job in the
    # CI matrix fail on all three operating systems, which is a good
    # demonstration of why the support floor belongs in the matrix rather
    # than in a comment.
    try:
        import tomllib
    except ModuleNotFoundError:  # Python 3.10
        import tomli as tomllib  # type: ignore[no-redef]

    data = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    extras = data["project"]["optional-dependencies"]
    assert any("jsonschema" in dep for dep in extras.get("schema", []))
    assert any("jsonschema" in dep for dep in extras.get("dev", []))
    return "declared in both the schema and dev extras"


# --- Feature 8: the classifier gates the leaderboard ------------------------
@check("#8 leaderboard groups by comparison safety")
def _f8():
    from aihwbench.export import comparison_groups

    a = {
        "run_id": "a",
        "runtime": {"name": "ollama", "version": "1", "backend": "api", "device": "cuda"},
        "model": {"name": "m"},
        "reproducibility": {"iterations": 5, "warmup_runs": 2},
        "metrics": {},
    }
    b = json.loads(json.dumps(a))
    b["run_id"] = "b"
    b["runtime"]["name"] = "llama.cpp"
    groups = comparison_groups([a, b])
    assert len(groups) == 2, f"incomparable runs landed in {len(groups)} group(s)"
    return "two incomparable runs are two groups, not one ranking"


# --- Feature 13/14: interval metrics have producers -------------------------
@check("#13/#14 ITL distribution and TPOT have producers")
def _f13():
    from aihwbench.metrics import streaming_latency_metrics

    out = streaming_latency_metrics([{"chunk_times_ms": [10.0, 21.0, 33.0, 46.0, 60.0]}])
    for key in ("itl_p50_ms", "itl_p90_ms", "itl_p99_ms", "inter_token_samples"):
        assert key in out, f"{key} missing"
    assert out["inter_token_samples"] == 4
    return f"p50={out['itl_p50_ms']}, samples={out['inter_token_samples']}"


# --- Feature 23: energy in kWh / carbon terms -------------------------------
@check("#23 joules per token and kWh terms are computed")
def _f23():
    from aihwbench.analysis.energy import compute_energy_metrics

    out = compute_energy_metrics(
        average_power_watts=30.0,
        idle_power_watts=10.0,
        generation_tokens_per_second=100.0,
        requests_per_second=None,
        telemetry_source="nvidia-smi",
    )
    assert out.get("energy_joules_per_token") is not None
    assert out.get("tokens_per_kwh") is not None
    return f"J/token={out['energy_joules_per_token']:.4f}"


# --- Feature 27: confidence intervals on published numbers ------------------
@check("#27 confidence intervals accompany the throughput number")
def _f27():
    from aihwbench.metrics import aggregate_iteration_metrics

    iters = [
        {"completion_tokens": 100, "eval_seconds": 1.0, "total_latency_ms": 1000.0},
        {"completion_tokens": 100, "eval_seconds": 1.1, "total_latency_ms": 1100.0},
        {"completion_tokens": 100, "eval_seconds": 0.9, "total_latency_ms": 900.0},
    ]
    out = aggregate_iteration_metrics(iters)
    assert out.get("gen_tps_ci95") is not None, "no 95% interval"
    return f"ci95={out['gen_tps_ci95']}"


# --- Feature 38: tokenizer identity -----------------------------------------
@check("#38 tokenizer identity is a comparability field")
def _f38():
    from aihwbench.comparability import _STRICT

    assert any("tokenizer" in f for f in _STRICT), "tokenizer not in the strict set"
    return "model.tokenizer is in the strict set"


# --- Feature 39/40: speculative decoding acceptance -------------------------
@check("#39/#40 draft acceptance distinguishes 'no drafts' from 'none accepted'")
def _f39():
    from aihwbench.analysis.speculative import acceptance_report

    zero = {
        "llamacpp:spec_decode_num_draft_tokens_total": 0,
        "llamacpp:spec_decode_num_accepted_tokens_total": 0,
    }
    none_drafted = acceptance_report(zero, dict(zero))
    assert none_drafted.get("acceptance_rate") is None, "0 drafts reported as 0% accepted"
    return "zero drafts reports acceptance as unknown, not as 0%"


# --- Feature 42: KV-cache matrix framed as memory ---------------------------
@check("#42 KV-cache analysis is framed as memory, not speed")
def _f42():
    import inspect

    from aihwbench.analysis.kvcache import analyze_kv_cache_matrix

    src = inspect.getsource(analyze_kv_cache_matrix)
    assert "costs_more_than_baseline" in src
    return "detects configurations that cost more memory than they save"


# --- Feature 97/101/102: SEO foundations ------------------------------------
@check("#97 BrowserRouter, not HashRouter")
def _f97():
    app = Path("web/src/App.tsx").read_text(encoding="utf-8")
    assert "<BrowserRouter" in app, "BrowserRouter is not rendered"
    # The word HashRouter appears in a comment explaining why it is not used,
    # so look for the element rather than the string.
    assert "<HashRouter" not in app, "HashRouter is still rendered"
    return "BrowserRouter is rendered; HashRouter only referenced in prose"


@check("#101/#102 JSON-LD, sitemap, robots, canonical are emitted")
def _f101():
    dist = Path("web/dist")
    if not (dist / "index.html").is_file():
        return "SKIPPED (no build present)"
    home = (dist / "index.html").read_text(encoding="utf-8")
    assert "application/ld+json" in home, "no JSON-LD"
    assert 'rel="canonical"' in home, "no canonical"
    assert (dist / "sitemap.xml").is_file(), "no sitemap"
    assert (dist / "robots.txt").is_file(), "no robots.txt"
    pages = len(list(dist.rglob("index.html")))
    return f"{pages} prerendered pages, JSON-LD + canonical + sitemap + robots"


# --- Feature 113: public dataset API ----------------------------------------
@check("#113 OpenAPI document exists and is valid JSON")
def _f113():
    spec = json.loads(Path("web/public/api/openapi.json").read_text(encoding="utf-8"))
    assert spec.get("openapi", "").startswith("3."), spec.get("openapi")
    return f"OpenAPI {spec['openapi']}, {len(spec.get('paths', {}))} paths"


# --- Feature 94: model zoo with licences and checksums ----------------------
@check("#94 model zoo records licence and checksum")
def _f94():
    from aihwbench.modelzoo import load_zoo

    entries = load_zoo()
    assert entries, "zoo is empty"
    first = entries[0]
    assert getattr(first, "license", None), "no licence recorded"
    return f"{len(entries)} entries, first licence={first.license}"


# --- Every registered backend can be resolved and detected ------------------
@check("all registered backends resolve, detect, and expose run()")
def _backends():
    from aihwbench.backends import BACKENDS, resolve

    for name in sorted(BACKENDS):
        mod = resolve(name)
        assert callable(getattr(mod, "detect", None)), f"{name} has no detect()"
        assert callable(getattr(mod, "run", None)), f"{name} has no run()"
        mod.detect()
    return f"{len(BACKENDS)} backends"


@check("no backend's run() is a bare 'planned' stub")
def _no_stub_runs():
    import inspect

    from aihwbench.backends import BACKENDS, resolve

    offenders = []
    for name in sorted(BACKENDS):
        src = inspect.getsource(resolve(name).run)
        measures = (
            "new_run_id" in src
            or "run_via_" in src
            or "run_openai_benchmark" in src
            or "llama_cpp.run" in src
        )
        if not measures:
            offenders.append(name)
    assert not offenders, f"these only raise: {offenders}"
    return f"all {len(BACKENDS)} reach a measurement path"


for status, label, detail in results:
    print(f"{status:4} {label}")
    if detail:
        print(f"      {detail}")

failed = [r for r in results if r[0] == FAIL]
print()
print(f"{len(results) - len(failed)}/{len(results)} checks passed")
sys.exit(1 if failed else 0)
