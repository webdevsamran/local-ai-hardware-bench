"""Experiment-identity fingerprint tests (algorithm version 2).

Pins that the fingerprint separates experiments by protocol, runtime and
hardware identity dimensions, ignores outcomes, and is deterministic.
"""

from __future__ import annotations

import re

from aihwbench.fingerprint import (
    FINGERPRINT_ALGORITHM_VERSION,
    find_duplicates,
    result_fingerprint,
)


def _base_result() -> dict:
    return {
        "run_id": "run-1",
        "schema_version": "2.0",
        "protocol_version": "1",
        "model": {"name": "Llama-3.2-1B", "checksum": "abc123", "format": "gguf"},
        "runtime": {
            "name": "llama.cpp",
            "backend": "llama-cpp",
            "version": "b4200",
            "device": "cuda",
        },
        "workload": {"id": "chat-short", "kind": "llm-generation", "version": "1.0"},
        "reproducibility": {
            "workload_type": "llm-generation",
            "prompt": "hello",
            "max_tokens": 128,
            "temperature": 0.7,
            "seed": 42,
        },
        "system": {
            "cpu": "AMD Ryzen 9 7940HS",
            "gpu": "AMD Radeon 780M",
            "os": "Windows 11",
            "ram_gb": 32,
        },
        "metrics": {"p50_latency_ms": 100.0},
    }


def test_fingerprint_is_deterministic_and_order_independent():
    a = result_fingerprint(_base_result())
    b = result_fingerprint(_base_result())
    assert a == b
    # Key order must not matter.
    reversed_dict = dict(reversed(list(_base_result().items())))
    assert result_fingerprint(reversed_dict) == a


def test_fingerprint_is_sha256_hex():
    assert re.fullmatch(r"[0-9a-f]{64}", result_fingerprint(_base_result()))


def test_algorithm_version_is_at_least_v2():
    assert FINGERPRINT_ALGORITHM_VERSION >= 2


def test_protocol_version_changes_identity():
    r1 = _base_result()
    r2 = _base_result()
    r2["protocol_version"] = "2"
    assert result_fingerprint(r1) != result_fingerprint(r2)


def test_runtime_version_changes_identity():
    r1 = _base_result()
    r2 = _base_result()
    r2["runtime"] = {**r1["runtime"], "version": "b4300"}
    assert result_fingerprint(r1) != result_fingerprint(r2)


def test_os_and_ram_change_identity():
    r1 = _base_result()
    r2 = _base_result()
    r2["system"] = {**r1["system"], "os": "Ubuntu 24.04", "ram_gb": 16}
    assert result_fingerprint(r1) != result_fingerprint(r2)


def test_workload_block_changes_identity():
    r1 = _base_result()
    r2 = _base_result()
    r2["workload"] = {**r1["workload"], "id": "rag"}
    assert result_fingerprint(r1) != result_fingerprint(r2)


def test_missing_fields_differ_from_present():
    r1 = _base_result()
    r2 = _base_result()
    del r2["system"]["ram_gb"]
    assert result_fingerprint(r1) != result_fingerprint(r2)


def test_metrics_and_run_id_do_not_change_identity():
    # Outcomes and artifact identifiers are not experiment identity: two
    # legitimate repeats of the same experiment must share a fingerprint.
    r1 = _base_result()
    r2 = _base_result()
    r2["run_id"] = "run-2"
    r2["metrics"] = {"p50_latency_ms": 105.5}
    assert result_fingerprint(r1) == result_fingerprint(r2)


def test_find_duplicates_groups_repeats_and_splits_experiments():
    r1 = _base_result()
    r2 = _base_result()
    r2["run_id"] = "run-2"
    r3 = _base_result()
    r3["run_id"] = "run-3"
    r3["reproducibility"] = {**r3["reproducibility"], "max_tokens": 256}
    groups = find_duplicates([r1, r2, r3])
    assert groups == [["run-1", "run-2"]]


def test_find_duplicates_empty_for_unique_results():
    assert find_duplicates([_base_result()]) == []
