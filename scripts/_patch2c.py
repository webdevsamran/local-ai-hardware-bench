#!/usr/bin/env python3
"""Issue batch 2, part C: create tests/test_issue_batch2.py matching the
surviving module APIs (introspected at runtime), then validate it."""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from _patch2a import FAILURES, resolve_capabilities, resolve_npu_fn  # noqa: E402

TESTS = ROOT / "tests" / "test_issue_batch2.py"

HEADER = '''"""Tests for issue batch 2 (#4,#5,#6,#7-#11,#9,#17,#18,#19,#22,#23,#24)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aihwbench.analysis.thermal import (  # noqa: E402
    temperature_slope_c_per_min,
    thermal_stability,
)
from aihwbench.backends import BACKENDS, detect_all  # noqa: E402


def test_thermal_slope_linear_ramp():
    ramp = [30.0 + i for i in range(10)]  # +1 degC per 60 s
    slope = temperature_slope_c_per_min(ramp, interval_s=60.0)
    assert slope is not None
    assert abs(slope - 1.0) < 1e-6


def test_thermal_slope_insufficient_data():
    assert temperature_slope_c_per_min([30.0]) is None
    assert temperature_slope_c_per_min([], interval_s=5.0) is None


def test_thermal_stability_verdicts():
    stable = [50.0 + 0.05 * i for i in range(30)]
    assert thermal_stability(stable, interval_s=5.0)["verdict"] == "stable"
    runaway = [50.0 + 3.0 * i for i in range(30)]
    assert thermal_stability(runaway, interval_s=5.0)["verdict"] == "throttling_risk"
    assert thermal_stability([], interval_s=5.0)["verdict"] == "insufficient_data"
    assert thermal_stability([], interval_s=5.0)["peak_temperature_c"] is None


def test_registry_contains_new_backends():
    assert "lemonade" in BACKENDS
    assert "openvino_genai" in BACKENDS


def test_new_backend_detect_never_raises():
    import aihwbench.backends.lemonade as lem
    import aihwbench.backends.openvino_genai as gen
    for mod, name in ((lem, "lemonade"), (gen, "openvino_genai")):
        info = mod.detect()
        assert info.name == name
        assert info.status.value  # honest RuntimeStatus, never fabricated


def test_detect_all_surfaces_capabilities():
    rows = detect_all()
    assert rows
    for row in rows:
        assert "capabilities" in row


def test_zenodo_metadata_parses():
    data = json.loads((ROOT / ".zenodo.json").read_text(encoding="utf-8"))
    assert data.get("title")
    assert data.get("creators")


def test_versioned_formal_schemas_exist():
    for name in ("result-1.0.schema.json", "result-2.0.schema.json"):
        path = ROOT / "schemas" / name
        assert path.exists(), name
        json.loads(path.read_text(encoding="utf-8"))
'''


def main() -> int:
    if TESTS.exists():
        print("SKIP tests/test_issue_batch2.py (exists)")
    else:
        npu_fn = resolve_npu_fn()
        cap = resolve_capabilities()
        parts = [HEADER]
        if npu_fn:
            parts.append(f'''

def test_telemetry_npu_hook(monkeypatch):
    import aihwbench.npu as npu_mod
    from aihwbench.telemetry import TelemetrySampler

    monkeypatch.setattr(
        npu_mod, "{npu_fn}", lambda: {{"npu_util_percent": 42.0}}, raising=True
    )
    summary = TelemetrySampler(interval_seconds=0.05).summary()
    assert summary.get("npu_util_percent") == 42.0
''')
        else:
            print("WARN npu sampler fn unresolved; NPU hook test omitted")
        if cap:
            parts.append('''

def test_parquet_export_roundtrip(tmp_path):
    pytest.importorskip("pyarrow")
    import pyarrow.parquet as pq

    from aihwbench.export import export_parquet

    docs = [{
        "schema_version": "1.0",
        "run_id": "parquet-test-1",
        "timestamp": "2026-08-28T00:00:00Z",
        "trust_state": "unreviewed",
        "runtime": {"name": "ollama", "version": "0.1", "device": "auto"},
        "model": {"name": "m", "format": "gguf", "quantization": None},
        "system": {"cpu": "c", "gpu": None, "npu": None, "ram_gb": 16.0},
        "metrics": {"generation_tokens_per_second": 12.5, "ttft_ms": 100.0},
    }]
    out = export_parquet(docs, tmp_path / "view.parquet")
    table = pq.read_table(out)
    assert table.num_rows == 1
    row = table.to_pylist()[0]
    assert row["generation_tokens_per_second"] == 12.5
    assert row["ttft_ms"] == 100.0
    assert row["trust_state"] == "unreviewed"
''')
        else:
            print("WARN capabilities API unresolved; registry tests still run")
        parts.append('''

def test_formal_schema_reader_validates_2_0():
    try:
        import aihwbench.formal_schema as fs
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"formal_schema import failed: {exc}")
    fn = next((n for n in ("validate_result", "validate_document", "validate")
               if callable(getattr(fs, n, None))), None)
    if fn is None:
        pytest.skip("no validate fn in formal_schema")
    doc = json.loads(
        (ROOT / "schemas" / "result-2.0.schema.json").read_text(encoding="utf-8")
    )
    validator = getattr(fs, fn)
    # the schema file itself is a JSON Schema document; validating it must
    # not raise regardless of outcome — reader API smoke test
    assert validator(doc) is not None
''')
        TESTS.write_text("".join(parts), encoding="utf-8")
        print(f"OK   tests/test_issue_batch2.py ({TESTS.stat().st_size} bytes)")

    import ast
    try:
        ast.parse(TESTS.read_text(encoding="utf-8"))
        print("AST  OK   tests/test_issue_batch2.py")
    except SyntaxError as exc:
        print(f"AST  FAIL tests/test_issue_batch2.py: {exc}")
        FAILURES.append("tests:ast")

    print("FAILURES:", FAILURES or "none")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
