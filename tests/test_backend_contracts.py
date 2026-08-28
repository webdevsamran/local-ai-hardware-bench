"""Backend measurement-contract tests (Phase A fix 6).

Proves the P0 backend measurement fixes without any real runtime
installed:

- ``resolve_input_specs`` resolves EVERY declared graph input
  (multi-input models), normalizes dtype vocabularies, pins dynamic
  dimensions, and fails closed on unsupported dtypes.
- ONNX Runtime input building feeds all declared inputs (fake session).
- llama.cpp token accounting uses ONLY the SSE usage object; streamed
  content chunks are recorded separately and never substitute tokens.
- llama.cpp server port is OS-assigned, not a hard-coded collision.
- LM Studio keeps engine counters and client wall-clock rates apart and
  labels the derivation via ``metric_source``.
- The new provenance fields validate against the semantic schema.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
from typing import Any

import numpy as np
import pytest

from aihwbench.backends import llama_cpp, lmstudio, onnxruntime
from aihwbench.backends.base import (
    BackendError,
    BenchmarkConfig,
    file_sha256,
    resolve_input_specs,
)

# ---------------------------------------------------------------------------
# resolve_input_specs — the shared multi-input graph feed resolver
# ---------------------------------------------------------------------------


def test_resolve_input_specs_resolves_every_declared_input() -> None:
    specs = resolve_input_specs(
        [
            ("pixels", "tensor(float)", [1, 3, 224, 224]),
            ("indices", "tensor(int64)", [4]),
        ]
    )
    assert set(specs) == {"pixels", "indices"}
    assert specs["pixels"] == {"shape": [1, 3, 224, 224], "dtype": "float32"}
    assert specs["indices"] == {"shape": [4], "dtype": "int64"}


def test_resolve_input_specs_pins_dynamic_and_invalid_dims_to_one() -> None:
    specs = resolve_input_specs([("x", "float32", ["batch", -1, 0, 2, True])])
    # strings, negatives, zero and bools all pin to 1; positives preserved
    assert specs["x"]["shape"] == [1, 1, 1, 2, 1]


def test_resolve_input_specs_normalizes_dtype_vocabularies() -> None:
    cases = {
        "tensor(int64)": "int64",
        "i32": "int32",
        "float": "float32",
        "double": "float64",
        "float16": "float16",
        "uint8": "uint8",
        "bool": "bool",
    }
    for raw, expected in cases.items():
        specs = resolve_input_specs([("x", raw, [1])])
        assert specs["x"]["dtype"] == expected, raw


@pytest.mark.parametrize("bad", ["tensor(bfloat16)", "bf16", "string"])
def test_resolve_input_specs_fails_closed_on_unsupported_dtypes(bad: str) -> None:
    with pytest.raises(BackendError):
        resolve_input_specs([("x", bad, [1])])


def test_resolve_input_specs_fails_closed_on_zero_inputs() -> None:
    with pytest.raises(BackendError, match="declares no inputs"):
        resolve_input_specs([])


# ---------------------------------------------------------------------------
# ONNX Runtime input building against a fake session (no onnxruntime pkg)
# ---------------------------------------------------------------------------


class _FakeInputMeta:
    def __init__(self, name: str, type_: str, shape: list[Any]) -> None:
        self.name = name
        self.type = type_
        self.shape = shape


class _FakeOrtSession:
    def __init__(self, inputs: list[_FakeInputMeta]) -> None:
        self._inputs = inputs

    def get_inputs(self) -> list[_FakeInputMeta]:
        return self._inputs


def test_ort_input_building_feeds_all_declared_inputs() -> None:
    session = _FakeOrtSession(
        [
            _FakeInputMeta("pixels", "tensor(float)", [1, 3, 8, 8]),
            _FakeInputMeta("mask", "tensor(int64)", ["batch", 2]),
            _FakeInputMeta("scale", "tensor(float)", [1]),
        ]
    )
    feed = onnxruntime._make_inputs(session)
    assert set(feed) == {"pixels", "mask", "scale"}
    assert feed["pixels"].shape == (1, 3, 8, 8) and feed["pixels"].dtype == np.float32
    assert feed["mask"].shape == (1, 2) and feed["mask"].dtype == np.int64
    assert feed["scale"].shape == (1,) and feed["scale"].dtype == np.float32


def test_ort_declared_inputs_manifest_preserves_declarations() -> None:
    session = _FakeOrtSession([_FakeInputMeta("x", "tensor(float)", ["seq", 4])])
    manifest = onnxruntime._declared_inputs(session)
    assert manifest == [{"name": "x", "type": "tensor(float)", "shape": ["seq", 4]}]


# ---------------------------------------------------------------------------
# file_sha256 — model identity
# ---------------------------------------------------------------------------


def test_file_sha256_matches_hashlib(tmp_path) -> None:
    model = tmp_path / "model.bin"
    payload = b"ggmf" + b"x" * 5000
    model.write_bytes(payload)
    assert file_sha256(model) == hashlib.sha256(payload).hexdigest()


# ---------------------------------------------------------------------------
# llama.cpp — usage-only token accounting, ephemeral port
# ---------------------------------------------------------------------------


class _FakeSseResponse:
    """Minimal urllib response: context manager iterating raw SSE lines."""

    def __init__(self, chunks: list[dict[str, Any]]) -> None:
        self._lines = [b"data: " + json.dumps(c).encode("utf-8") for c in chunks]
        self._lines.append(b"data: [DONE]")

    def __enter__(self) -> _FakeSseResponse:
        return self

    def __exit__(self, *exc: Any) -> bool:
        return False

    def __iter__(self) -> Any:
        return iter(self._lines)


def _patch_urlopen(
    monkeypatch: pytest.MonkeyPatch, module: Any, chunks: list[dict[str, Any]]
) -> None:
    monkeypatch.setattr(module.urllib.request, "urlopen", lambda *a, **k: _FakeSseResponse(chunks))


def test_llamacpp_tokens_come_only_from_usage_object(monkeypatch: pytest.MonkeyPatch) -> None:
    # 12 streamed content chunks but the engine usage object counts 7 tokens:
    # chunks are transport artifacts and must never substitute for tokens.
    content = {"choices": [{"delta": {"content": "tok"}}]}
    chunks = [dict(content) for _ in range(12)]
    chunks.append({"choices": [], "usage": {"completion_tokens": 7, "prompt_tokens": 3}})
    _patch_urlopen(monkeypatch, llama_cpp, chunks)

    handle = llama_cpp.LlamaServerHandle(
        "llama-server", "m.gguf", BenchmarkConfig(model="m"), port=1
    )
    handle.base_url = "http://127.0.0.1:1"  # no server started; response is fake
    detail = llama_cpp._chat_stream(handle, BenchmarkConfig(model="m"))
    assert detail["completion_tokens"] == 7
    assert detail["prompt_tokens"] == 3
    assert detail["stream_content_chunks"] == 12
    assert detail["ttft_ms"] is not None and detail["ttft_ms"] >= 0.0


def test_llamacpp_without_usage_tokens_stay_null(monkeypatch: pytest.MonkeyPatch) -> None:
    chunks = [{"choices": [{"delta": {"content": "tok"}}]} for _ in range(4)]
    _patch_urlopen(monkeypatch, llama_cpp, chunks)
    handle = llama_cpp.LlamaServerHandle(
        "llama-server", "m.gguf", BenchmarkConfig(model="m"), port=1
    )
    handle.base_url = "http://127.0.0.1:1"
    detail = llama_cpp._chat_stream(handle, BenchmarkConfig(model="m"))
    # No usage object -> tokens stay null (never estimated from chunk count)
    assert detail["completion_tokens"] is None
    assert detail["stream_content_chunks"] == 4


def test_llamacpp_port_is_os_assigned_not_hardcoded() -> None:
    port = llama_cpp._free_port()
    assert 1024 <= port <= 65535
    src = pathlib.Path(llama_cpp.__file__).read_text(encoding="utf-8")
    assert "8123" not in src, "fixed port re-introduced in llama.cpp backend"


# ---------------------------------------------------------------------------
# LM Studio — usage tokens kept, wall-clock derivation labeled
# ---------------------------------------------------------------------------


def test_lmstudio_usage_tokens_with_wall_clock_decode_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    content = {"choices": [{"delta": {"content": "w"}}]}
    chunks = [dict(content) for _ in range(6)]
    chunks.append({"choices": [], "usage": {"completion_tokens": 5, "prompt_tokens": 2}})
    _patch_urlopen(monkeypatch, lmstudio, chunks)
    detail = lmstudio._chat_stream("m", "p", BenchmarkConfig(model="m"))
    assert detail["completion_tokens"] == 5
    assert detail["prompt_tokens"] == 2
    assert detail["eval_seconds"] is not None and detail["eval_seconds"] >= 0.0
    # Engine prompt-eval timing does not exist -> stays null, never invented
    assert detail["prompt_eval_seconds"] is None


def test_lmstudio_without_usage_tokens_stay_null(monkeypatch: pytest.MonkeyPatch) -> None:
    chunks = [{"choices": [{"delta": {"content": "w"}}]} for _ in range(3)]
    _patch_urlopen(monkeypatch, lmstudio, chunks)
    detail = lmstudio._chat_stream("m", "p", BenchmarkConfig(model="m"))
    assert detail["completion_tokens"] is None
    assert detail["eval_seconds"] is None


@pytest.mark.parametrize("module", [llama_cpp, lmstudio], ids=["llama.cpp", "lmstudio"])
def test_metric_source_labels_generation_rate_as_client_wall_clock(module: Any) -> None:
    block = module.metric_source_block()
    assert block["completion_tokens"] == "engine_usage"
    assert block["generation_tokens_per_second"] == "client_wall_clock"
    assert isinstance(block["note"], str) and block["note"]


# ---------------------------------------------------------------------------
# New provenance fields must pass semantic validation
# ---------------------------------------------------------------------------


def test_new_provenance_fields_pass_semantic_validation() -> None:
    from aihwbench.schemas import validate_or_raise

    result_path = (
        pathlib.Path(__file__).resolve().parent.parent
        / "results"
        / "published"
        / "ollama-1787388930.json"
    )
    if not result_path.exists():
        pytest.skip("published results not present in this checkout")
    doc = json.loads(result_path.read_text(encoding="utf-8"))
    doc["metrics"]["metric_source"] = lmstudio.metric_source_block()
    doc["runtime"]["backend"] = "llama-server-openai"
    doc["runtime"]["port"] = 0  # 0 -> OS-assigned in the new backend contract
    doc["iterations"][0]["stream_content_chunks"] = 11
    doc["model"]["checksum"] = hashlib.sha256(b"x").hexdigest()
    validate_or_raise(doc)
