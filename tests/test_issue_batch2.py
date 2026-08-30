"""Issue batch 2 tests: thermal stability (#19), parquet export (#17),
NPU hooks (#18), formal schema 2.0 (#22), GenAI/Lemonade backends (#6/#9).
"""

import json
import pathlib

import pytest

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11; tomli is in the dev extra
    import tomli as tomllib  # type: ignore[no-redef]

from aihwbench.analysis.thermal import analyze_thermal_stability, temperature_slope_c_per_min


def test_temperature_slope_flat_is_zero():
    t = [0.0, 60.0, 120.0]
    c = [55.0, 55.0, 55.0]
    assert temperature_slope_c_per_min(t, c) == pytest.approx(0.0, abs=1e-6)


def test_temperature_slope_rising():
    t = [0.0, 600.0]
    c = [50.0, 60.0]  # 10 C over 10 min = 1.0 C/min
    assert temperature_slope_c_per_min(t, c) == pytest.approx(1.0, abs=1e-3)


def test_temperature_slope_insufficient_points():
    assert temperature_slope_c_per_min([0.0], [50.0]) is None
    assert temperature_slope_c_per_min([], []) is None
    assert temperature_slope_c_per_min([0.0], []) is None  # length mismatch


def test_temperature_slope_rejects_unsorted():
    with pytest.raises(ValueError):
        temperature_slope_c_per_min([0.0, 10.0, 5.0], [50.0, 51.0, 52.0])


def test_thermal_stability_analysis():
    t = [0.0, 60.0, 120.0, 180.0, 240.0]
    tps = [10.0, 10.2, 9.8, 10.0, 9.9]
    c = [55.0, 55.5, 55.0, 55.2, 55.1]
    s = analyze_thermal_stability(t, tps, c)
    assert s["peak_throughput_tps"] == pytest.approx(10.2)
    assert s["max_temperature_c"] == pytest.approx(55.5)
    assert s["final_temperature_c"] == pytest.approx(55.1)
    assert s["temperature_slope_c_per_min"] is not None
    assert s["temperature_curve"] and "temp_c" in s["temperature_curve"][0]


def test_thermal_stability_insufficient_samples():
    s = analyze_thermal_stability([0.0], [10.0], [55.0])
    assert s["peak_throughput_tps"] is None
    assert s["temperature_slope_c_per_min"] is None
    assert "reason" in s


def test_thermal_stability_throttle_detection():
    t = [0.0, 60.0]
    tps = [10.0, 10.0]
    c = [84.0, 86.0]
    s = analyze_thermal_stability(t, tps, c, throttle_temp_c=85.0)
    assert s["time_to_throttle_s"] == pytest.approx(60.0)


def test_npu_hooks_are_honest_none():
    from aihwbench.npu import NPU_FIELDS, enrich_with_npu, npu_telemetry

    d = npu_telemetry()
    assert "npu_device" in d
    for k in NPU_FIELDS:
        assert k in d
        assert d[k] is None

    # enrichment never fabricates values and never mutates its input
    base = {"ram_used_mb": 12}
    merged = enrich_with_npu(base)
    assert base == {"ram_used_mb": 12}
    assert merged["ram_used_mb"] == 12
    for k in NPU_FIELDS:
        assert merged[k] is None


def test_npu_telemetry_mirrors_detected_device():
    from aihwbench.npu import npu_telemetry

    d = npu_telemetry({"npu": "Intel AI Boost"})
    assert d["npu_device"] == "Intel AI Boost"


def test_parquet_export(tmp_path):
    pytest.importorskip("pyarrow")
    from aihwbench.export import export_parquet

    doc = {
        "run_id": "t1",
        "schema_version": "1.0",
        "timestamp": "2026-01-01T00:00:00Z",
        "trust_state": "verified",
        "system": {"cpu": "X", "cpu_cores_logical": 8},
        "metrics": {"ttft_ms": 12.5},
    }
    out = export_parquet([doc], tmp_path / "r.parquet")
    assert out.exists()
    import pyarrow.parquet as pq

    tbl = pq.read_table(out)
    assert tbl.num_rows == 1
    assert "system_cpu" in tbl.column_names
    assert "metrics_ttft_ms" in tbl.column_names  # {section}_{key} naming scheme


def test_parquet_extra_registered():
    pyproject = pathlib.Path(__file__).resolve().parent.parent / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    assert "parquet" in data["project"]["optional-dependencies"]


def test_cli_export_has_parquet_flag():
    cli = pathlib.Path(__file__).resolve().parent.parent / "aihwbench" / "cli" / "dataset.py"
    text = cli.read_text(encoding="utf-8")
    assert "--parquet" in text


def test_genai_and_lemonade_registered():
    from aihwbench.backends import BACKENDS, resolve

    for name in ("openvino_genai", "lemonade"):
        assert name in BACKENDS
        mod = resolve(name)
        assert callable(getattr(mod, "detect", None))
        assert callable(getattr(mod, "run", None))


def test_formal_schema_20_exists():
    pytest.importorskip("jsonschema")
    schema_path = (
        pathlib.Path(__file__).resolve().parent.parent / "schemas" / "result-2.0.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    assert "2.0" in json.dumps(schema["properties"]["schema_version"])
    assert "required" in schema
