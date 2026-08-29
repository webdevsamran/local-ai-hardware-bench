"""Issue batch 2 tests: thermal stability (#19), parquet export (#17),
NPU hooks (#18), formal schema 2.0 (#22), GenAI/Lemonade backends (#6/#9).
"""

import json
import pathlib
import tomllib

import pytest

from aihwbench.analysis.thermal import temperature_slope_c_per_min, thermal_stability


def test_temperature_slope_flat_is_zero():
    samples = [(0, 55.0), (60, 55.0), (120, 55.0)]
    assert temperature_slope_c_per_min(samples) == pytest.approx(0.0, abs=1e-6)


def test_temperature_slope_rising():
    samples = [(0, 50.0), (600, 60.0)]  # 10 C over 10 min = 1.0 C/min
    assert temperature_slope_c_per_min(samples) == pytest.approx(1.0, abs=1e-3)


def test_temperature_slope_insufficient_points():
    assert temperature_slope_c_per_min([(0, 50.0)]) is None
    assert temperature_slope_c_per_min([]) is None
    assert temperature_slope_c_per_min(None) is None


def test_thermal_stability_classification():
    stable = thermal_stability([(0, 55.0), (120, 55.5), (240, 55.0)])
    assert stable["classification"] == "stable"
    rising = thermal_stability([(0, 50.0), (600, 62.0)])
    assert rising["classification"] == "rising"
    fast = thermal_stability([(0, 50.0), (60, 60.0), (120, 72.0)])
    assert fast["classification"] == "throttling_risk"
    none = thermal_stability([(0, 50.0)])
    assert none["classification"] == "insufficient_data"
    assert none["slope_c_per_min"] is None


def test_thermal_stability_accepts_dicts():
    s = thermal_stability(
        [
            {"elapsed_s": 0, "temperature_c": 50.0},
            {"elapsed_s": 60, "temperature_c": 50.1},
        ]
    )
    assert s["classification"] == "stable"
    assert s["peak_temperature_c"] == pytest.approx(50.1)
    assert s["final_temperature_c"] == pytest.approx(50.1)


def test_npu_module_shape():
    from aihwbench.npu import detect_npu, sample_npu_telemetry

    d = detect_npu()
    assert isinstance(d, dict) and "present" in d
    t = sample_npu_telemetry()
    assert isinstance(t, dict)
    for k in ("npu_util_percent", "npu_temperature_c", "npu_power_watts"):
        assert k in t and (t[k] is None or isinstance(t[k], (int, float)))


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
    assert "metric_ttft_ms" in tbl.column_names


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
