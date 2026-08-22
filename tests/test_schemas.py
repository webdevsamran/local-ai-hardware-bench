"""Tests for result schema validation."""

from benchmark.schemas import SCHEMA_VERSION, validate_result


def make_valid_result() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": "test-run-1",
        "timestamp": "2026-01-01T00:00:00Z",
        "git_commit": None,
        "system": {
            "os": "Windows 11",
            "os_version": "10.0.26200",
            "cpu": "Test CPU",
            "cpu_cores_physical": 8,
            "cpu_cores_logical": 16,
            "gpu": "Test GPU",
            "gpu_vram_mb": 8192,
            "npu": None,
            "ram_gb": 32.0,
            "platform_name": "Test Platform",
        },
        "runtime": {"name": "ollama", "version": "0.1.0", "backend": "http", "device": "cuda"},
        "model": {
            "name": "m",
            "format": "gguf",
            "quantization": "q4_K_M",
            "parameters": "0.5B",
            "checksum": "abc",
        },
        "metrics": {
            "ttft_ms": 12.5,
            "generation_tokens_per_second": 40.0,
            "p50_latency_ms": 100.0,
            "p95_latency_ms": 150.0,
            "peak_ram_mb": None,
            "average_power_watts": None,
            "performance_per_watt": None,
        },
    }


def test_valid_result_passes():
    assert validate_result(make_valid_result()) == []


def test_missing_required_top_level_field():
    data = make_valid_result()
    del data["metrics"]
    errors = validate_result(data)
    assert any("metrics" in e for e in errors)


def test_wrong_schema_version_rejected():
    data = make_valid_result()
    data["schema_version"] = "9.9"
    errors = validate_result(data)
    assert any("schema_version" in e for e in errors)


def test_metric_wrong_type_rejected():
    data = make_valid_result()
    data["metrics"]["ttft_ms"] = "fast"
    errors = validate_result(data)
    assert any("ttft_ms" in e for e in errors)


def test_bool_not_accepted_as_number():
    data = make_valid_result()
    data["metrics"]["ttft_ms"] = True
    errors = validate_result(data)
    assert any("ttft_ms" in e for e in errors)


def test_null_metrics_allowed():
    data = make_valid_result()
    data["metrics"] = {k: None for k in data["metrics"]}
    assert validate_result(data) == []


def test_non_dict_rejected():
    assert validate_result([1, 2, 3]) != []
    assert validate_result("nope") != []


def test_negative_ram_rejected():
    data = make_valid_result()
    data["system"]["ram_gb"] = -1
    errors = validate_result(data)
    assert any("ram_gb" in e for e in errors)


def test_optional_inner_fields_may_be_absent():
    data = make_valid_result()
    # Inner fields are optional; removing them must not produce errors.
    for key in ("npu", "platform_name", "gpu_vram_mb"):
        del data["system"][key]
    del data["model"]["checksum"]
    assert validate_result(data) == []


def test_missing_required_sections_flagged():
    data = make_valid_result()
    for key in ("system", "runtime", "model", "metrics"):
        del data[key]
    errors = validate_result(data)
    for section in ("system", "runtime", "model", "metrics"):
        assert any(section in e for e in errors)
