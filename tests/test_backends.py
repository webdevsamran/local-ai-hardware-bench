"""Tests for backend detection and unavailable-backend handling."""

from aihwbench.backends import (
    BACKENDS,
    BackendError,
    BenchmarkConfig,
    RuntimeStatus,
    detect_all,
    resolve,
)
from aihwbench.backends.base import BackendInfo


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


def test_lmstudio_registered_and_resolvable():
    assert "lmstudio" in BACKENDS
    assert resolve("lms") is BACKENDS["lmstudio"]
    info = BACKENDS["lmstudio"].detect()
    assert isinstance(info, BackendInfo)
    # On CI there is no LM Studio server running.
    assert info.status in {RuntimeStatus.NOT_INSTALLED, RuntimeStatus.AVAILABLE}


def test_lmstudio_run_raises_without_server(monkeypatch):
    import aihwbench.backends.lmstudio as lm

    monkeypatch.setattr(
        lm,
        "detect",
        lambda: BackendInfo("lmstudio", RuntimeStatus.NOT_INSTALLED, None, "no server"),
    )
    try:
        lm.run(BenchmarkConfig(model="x"), {})
    except BackendError as exc:
        assert "not available" in str(exc)
    else:
        raise AssertionError("expected BackendError")


def test_mlx_off_platform_is_hardware_required(monkeypatch):
    import aihwbench.backends.mlx as mlx_mod

    monkeypatch.setattr(mlx_mod.platform, "system", lambda: "Windows")
    info = mlx_mod.detect()
    assert info.status is RuntimeStatus.HARDWARE_REQUIRED


def test_mlx_run_raises_cleanly(monkeypatch):
    import aihwbench.backends.mlx as mlx_mod

    monkeypatch.setattr(mlx_mod.platform, "system", lambda: "Windows")
    try:
        mlx_mod.run(BenchmarkConfig(model="dummy"), {})
    except BackendError as exc:
        assert "not available" in str(exc) or "planned" in str(exc).lower()
    else:
        raise AssertionError("expected BackendError")
