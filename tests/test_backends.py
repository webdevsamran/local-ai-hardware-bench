"""Tests for backend detection and unavailable-backend handling."""

from benchmark.backends import (
    BACKENDS,
    BackendError,
    BenchmarkConfig,
    RuntimeStatus,
    detect_all,
    resolve,
)
from benchmark.backends.base import BackendInfo


def test_all_registered_backends_detect_without_crashing():
    results = detect_all()
    names = {r["name"] for r in results}
    assert names == set(BACKENDS.keys())
    for result in results:
        # Every status must be a valid enum value
        assert result["status"] in {s.value for s in RuntimeStatus}


def test_resolve_known_and_aliases():
    assert resolve("ollama") is BACKENDS["ollama"]
    assert resolve("llamacpp") is BACKENDS["llama.cpp"]
    assert resolve("LLAMA.CPP") is BACKENDS["llama.cpp"]


def test_resolve_unknown_raises():
    try:
        resolve("does-not-exist")
    except BackendError:
        pass
    else:
        raise AssertionError("expected BackendError")


def test_backend_info_as_dict():
    info = BackendInfo("x", RuntimeStatus.NOT_INSTALLED, None, "detail")
    d = info.as_dict()
    assert d["status"] == "NOT_INSTALLED"
    assert d["version"] is None


def test_unavailable_backend_run_raises_backend_error():
    # qnn requires hardware that CI does not have; run() must fail cleanly.
    config = BenchmarkConfig(model="dummy")
    system = {"os": "test"}
    try:
        BACKENDS["qnn"].run(config, system)
    except BackendError as exc:
        assert "not available" in str(exc) or "planned" in str(exc).lower()
    else:
        raise AssertionError("expected BackendError")
