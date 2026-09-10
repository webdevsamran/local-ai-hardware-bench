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
import importlib
import json
import pathlib
from typing import Any

import numpy as np
import pytest

from aihwbench.backends import llama_cpp, lmstudio, onnxruntime
from aihwbench.backends.base import (
    BackendError,
    BenchmarkConfig,
    RuntimeStatus,
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


# --- Issue #5: Ollama load time comes only from the engine's load_duration ---


class _FakeOllamaResponse:
    """Context-manager byte-line response mimicking /api/generate streaming."""

    def __init__(self, lines: list[bytes]) -> None:
        self._lines = lines

    def __enter__(self) -> _FakeOllamaResponse:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def __iter__(self):
        return iter(self._lines)


def _ollama_stream_lines(load_duration_ns: int | None) -> list[bytes]:
    lines = [json.dumps({"response": "Hello", "done": False}).encode("utf-8")]
    final: dict[str, Any] = {
        "done": True,
        "eval_count": 42,
        "eval_duration": 1_000_000_000,
    }
    if load_duration_ns is not None:
        final["load_duration"] = load_duration_ns
    lines.append(json.dumps(final).encode("utf-8"))
    return lines


def test_ollama_load_time_from_engine_counter(monkeypatch: pytest.MonkeyPatch) -> None:
    from aihwbench.backends import ollama

    monkeypatch.setattr(
        ollama.urllib.request,
        "urlopen",
        lambda request, timeout: _FakeOllamaResponse(_ollama_stream_lines(250_000_000)),
    )
    it = ollama._generate_stream("m", "prompt", BenchmarkConfig(model="m"))
    assert it["load_time_ms"] == 250.0


def test_ollama_load_time_stays_null_when_engine_reports_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from aihwbench.backends import ollama

    monkeypatch.setattr(
        ollama.urllib.request,
        "urlopen",
        lambda request, timeout: _FakeOllamaResponse(_ollama_stream_lines(None)),
    )
    it = ollama._generate_stream("m", "prompt", BenchmarkConfig(model="m"))
    assert it["load_time_ms"] is None  # never estimated (#5)


def test_ollama_load_time_aggregates_into_metrics() -> None:
    from aihwbench.metrics import aggregate_iteration_metrics

    metrics = aggregate_iteration_metrics(
        [{"load_time_ms": 250.0, "completion_tokens": 42, "eval_seconds": 1.0}]
    )
    assert metrics["load_time_ms"] == 250.0


# ---------------------------------------------------------------------------
# vLLM / SGLang — the serving engines Bench360 measures, on consumer hardware
# ---------------------------------------------------------------------------
#
# Neither engine runs on Windows, so nothing here can be exercised against a
# real server on the reference machine. What these tests pin is the part that
# would go quietly wrong rather than fail: tokens taken from the wrong place,
# a rate presented as an engine counter, or a version invented for a server
# that does not report one.


def _openai_chunks(content_chunks: int, usage: dict[str, Any] | None) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = [
        {"choices": [{"delta": {"content": "tok"}}]} for _ in range(content_chunks)
    ]
    if usage is not None:
        chunks.append({"choices": [], "usage": usage})
    return chunks


@pytest.mark.parametrize("name", ["vllm", "sglang"])
def test_openai_backends_take_tokens_only_from_usage(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    """Chunks are transport artifacts; a chunk is not a token.

    These servers emit multi-token chunks under load, so counting deltas
    inflates throughput exactly when the machine is busiest.
    """
    from aihwbench.backends import openai_server

    module = importlib.import_module(f"aihwbench.backends.{name}")
    chunks = _openai_chunks(11, {"completion_tokens": 6, "prompt_tokens": 4})
    monkeypatch.setattr(
        openai_server.urllib.request, "urlopen", lambda *a, **k: _FakeSseResponse(chunks)
    )

    detail = openai_server.chat_stream(module.SERVER, "m", "p", BenchmarkConfig(model="m"))
    assert detail["completion_tokens"] == 6
    assert detail["prompt_tokens"] == 4
    # One arrival time per content chunk, for the inter-token distribution.
    assert len(detail["chunk_times_ms"]) == 11
    # Both describe the first content chunk; they are rounded to different
    # precisions (2dp and 3dp), matching the Ollama backend's convention.
    assert detail["ttft_ms"] == pytest.approx(detail["chunk_times_ms"][0], abs=0.01)


@pytest.mark.parametrize("name", ["vllm", "sglang"])
def test_openai_backends_leave_tokens_null_without_usage(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    from aihwbench.backends import openai_server

    module = importlib.import_module(f"aihwbench.backends.{name}")
    monkeypatch.setattr(
        openai_server.urllib.request,
        "urlopen",
        lambda *a, **k: _FakeSseResponse(_openai_chunks(4, None)),
    )

    detail = openai_server.chat_stream(module.SERVER, "m", "p", BenchmarkConfig(model="m"))
    assert detail["completion_tokens"] is None
    # No numerator means no rate: the decode window is withheld rather than
    # divided into an unknown token count.
    assert detail["eval_seconds"] is None


@pytest.mark.parametrize("name", ["vllm", "sglang"])
def test_openai_backends_label_the_rate_as_wall_clock(name: str) -> None:
    from aihwbench.backends import openai_server

    module = importlib.import_module(f"aihwbench.backends.{name}")
    block = openai_server.metric_source_block(module.SERVER)
    assert block["generation_tokens_per_second"] == "client_wall_clock"
    assert block["completion_tokens"] == "engine_usage"
    # It includes the HTTP stack, so it is not llama-bench's number.
    assert "not comparable" in block["note"]


@pytest.mark.parametrize("name", ["vllm", "sglang"])
def test_openai_backends_report_unavailable_when_no_server_runs(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    from aihwbench.backends import openai_server

    module = importlib.import_module(f"aihwbench.backends.{name}")
    monkeypatch.setattr(openai_server, "_api_get", lambda *a, **k: None)

    info = module.detect()
    assert info.status is not RuntimeStatus.AVAILABLE
    assert info.version is None
    # The hint must say how to start one, not merely that it is absent.
    assert "server" in info.detail.lower()


def test_openai_backend_version_is_null_when_unreported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SGLang serves no /version. Inventing one would hide a real difference.

    `runtime.version` moves a pair from strictly to conditionally comparable,
    so a fabricated value would let two runs on different builds pass as one.
    """
    from aihwbench.backends import openai_server, sglang

    def fake_get(server: Any, path: str, timeout: float = 5.0) -> Any:
        if path == "/v1/models":
            return {"data": [{"id": "m"}]}
        return None  # no /version endpoint

    monkeypatch.setattr(openai_server, "_api_get", fake_get)
    info = sglang.detect()
    assert info.status is RuntimeStatus.AVAILABLE
    assert info.version is None


def test_openai_backends_do_not_launch_a_server() -> None:
    """Startup flags decide what is measured, so the operator chooses them.

    Tensor parallelism, GPU memory fraction, quantization and KV-cache dtype
    are all set at launch. A benchmark that started the server itself would be
    reporting on a configuration nobody chose.
    """
    for name in ("vllm", "sglang"):
        src = pathlib.Path(
            importlib.import_module(f"aihwbench.backends.{name}").__file__
        ).read_text(encoding="utf-8")
        assert "subprocess" not in src
        assert "Popen" not in src


@pytest.mark.parametrize("name", ["vllm", "sglang"])
def test_openai_backends_honour_a_host_override(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    """A machine serving two engines cannot give both the same port."""
    monkeypatch.setenv(f"AIHWBENCH_{name.upper()}_HOST", "http://example.invalid:9999")
    module = importlib.reload(importlib.import_module(f"aihwbench.backends.{name}"))
    try:
        assert module.SERVER.host == "http://example.invalid:9999"
    finally:
        monkeypatch.delenv(f"AIHWBENCH_{name.upper()}_HOST")
        importlib.reload(module)


# ---------------------------------------------------------------------------
# Ollama model identity — recorded, not guessed, and not left null
# ---------------------------------------------------------------------------
#
# `quantization` and `parameters` were hardcoded to None while `/api/tags` had
# been returning `details.quantization_level` and `details.parameter_size` all
# along. `model.quantization` is in the comparison-safety classifier's strict
# set, so null on both sides meant the two agreed about it: served under a name
# that does not encode the quantization, two different quantizations compared
# as STRICTLY_COMPARABLE with no reasons given.


def _tags_response(details: dict[str, Any] | None) -> dict[str, Any]:
    entry: dict[str, Any] = {"name": "m:tag", "digest": "sha256:abc"}
    if details is not None:
        entry["details"] = details
    return {"models": [entry]}


def test_ollama_records_the_quantization_the_api_reports(monkeypatch: pytest.MonkeyPatch) -> None:
    from aihwbench.backends import ollama

    monkeypatch.setattr(
        ollama,
        "_api_get",
        lambda *_a, **_k: _tags_response(
            {
                "quantization_level": "Q4_K_M",
                "parameter_size": "494.03M",
                "family": "qwen2",
                "format": "gguf",
            }
        ),
    )
    identity = ollama.model_identity("m:tag")
    # Lower-cased to match the vocabulary the fit estimator and dashboard use.
    assert identity["quantization"] == "q4_k_m"
    assert identity["parameters"] == "494.03M"
    assert identity["family"] == "qwen2"


def test_ollama_leaves_identity_null_when_the_api_says_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Absent stays absent. A guessed quantization is worse than none."""
    from aihwbench.backends import ollama

    monkeypatch.setattr(ollama, "_api_get", lambda *_a, **_k: _tags_response(None))
    identity = ollama.model_identity("m:tag")
    assert identity["quantization"] is None
    assert identity["parameters"] is None


def test_ollama_never_parses_the_quantization_out_of_the_tag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The tag says q4_K_M; the API does not. The result must stay null.

    Parsing tags would give `:latest` and any renamed model a confident wrong
    answer, and a wrong quantization is worse than a missing one -- it makes
    two different models compare as one.
    """
    from aihwbench.backends import ollama

    monkeypatch.setattr(ollama, "_api_get", lambda *_a, **_k: {"models": []})
    identity = ollama.model_identity("qwen2.5:0.5b-instruct-q4_K_M")
    assert identity["quantization"] is None


def test_recorded_quantization_closes_the_comparison_hole() -> None:
    """Same served name, different quantization, now caught."""
    from aihwbench.comparability import compare_classification

    base = {
        "model": {"name": "qwen2.5-0.5b", "quantization": "q4_k_m"},
        "runtime": {"name": "ollama", "backend": "ollama-http-api", "device": "cuda"},
        "reproducibility": {"iterations": 8, "warmup_runs": 3},
    }
    other = {
        "model": {"name": "qwen2.5-0.5b", "quantization": "q8_0"},
        "runtime": {"name": "ollama", "backend": "ollama-http-api", "device": "cuda"},
        "reproducibility": {"iterations": 8, "warmup_runs": 3},
    }
    verdict = compare_classification(base, other)
    assert verdict["classification"] == "NOT_COMPARABLE"
    assert any("quantization" in reason for reason in verdict["reasons"])


def test_two_nulls_would_still_have_agreed() -> None:
    """Why recording it mattered, stated as the defect it was.

    `_same(None, None)` is True by design, so leaving the field null made two
    different quantizations indistinguishable to the classifier.
    """
    from aihwbench.comparability import compare_classification

    shared = {
        "runtime": {"name": "ollama", "backend": "ollama-http-api", "device": "cuda"},
        "reproducibility": {"iterations": 8, "warmup_runs": 3},
    }
    a = {"model": {"name": "qwen2.5-0.5b", "quantization": None}, **shared}
    b = {"model": {"name": "qwen2.5-0.5b", "quantization": None}, **shared}
    assert compare_classification(a, b)["classification"] == "STRICTLY_COMPARABLE"


# ---------------------------------------------------------------------------
# runtime.device records what ran, not what was typed
# ---------------------------------------------------------------------------
#
# `runtime.device` held `config.device` verbatim, and it is in the
# comparison-safety classifier's strict set. Two ONNX Runtime runs on the same
# silicon — both landing on CPUExecutionProvider — were NOT_COMPARABLE because
# one passed `--device cpu` and the other took the `auto` default. A split
# created by how someone spelled a flag is exactly the false distinction the
# classifier exists to avoid making.


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("CPUExecutionProvider", "cpu"),
        ("DmlExecutionProvider", "dml"),
        ("CUDAExecutionProvider", "cuda"),
        ("TensorrtExecutionProvider", "cuda"),
        ("CPU", "cpu"),
        ("AUTO", "auto"),
        ("NPU", "npu"),
    ],
)
def test_resolved_device_maps_what_ran_to_the_recorded_vocabulary(name: str, expected: str) -> None:
    from aihwbench.backends.base import resolved_device

    assert resolved_device(name) == expected


def test_openvino_device_ordinals_do_not_split_one_machine() -> None:
    """`GPU.0` and `GPU.1` identify which card; `system.gpu` already says.

    Keeping the ordinal in `runtime.device` would make two runs on a
    machine's only GPU incomparable if OpenVINO enumerated it differently.
    """
    from aihwbench.backends.base import resolved_device

    assert resolved_device("GPU.0") == "gpu"
    assert resolved_device("GPU.1") == "gpu"


def test_an_unmappable_device_name_yields_none() -> None:
    """So the caller falls back to the requested value instead of guessing."""
    from aihwbench.backends.base import resolved_device

    assert resolved_device("SomeFutureExecutionProvider") is None
    assert resolved_device("") is None
    assert resolved_device(None) is None


def test_auto_and_explicit_cpu_are_comparable_once_resolved() -> None:
    """The defect, stated as the comparison it used to break."""
    from aihwbench.comparability import compare_classification

    shared = {
        "model": {"name": "m.onnx", "quantization": None},
        "reproducibility": {"iterations": 8, "warmup_runs": 3},
    }
    took_default = {
        "runtime": {
            "name": "onnxruntime",
            "backend": "execution-providers:CPUExecutionProvider",
            "device": "cpu",
            "device_requested": "auto",
        },
        **shared,
    }
    asked_explicitly = {
        "runtime": {
            "name": "onnxruntime",
            "backend": "execution-providers:CPUExecutionProvider",
            "device": "cpu",
            "device_requested": "cpu",
        },
        **shared,
    }
    assert (
        compare_classification(took_default, asked_explicitly)["classification"]
        == "STRICTLY_COMPARABLE"
    )


def test_genuinely_different_devices_still_split() -> None:
    """Resolving must not collapse a real difference."""
    from aihwbench.comparability import compare_classification

    shared = {
        "model": {"name": "m.onnx", "quantization": None},
        "reproducibility": {"iterations": 8, "warmup_runs": 3},
    }
    on_cpu = {
        "runtime": {
            "name": "onnxruntime",
            "backend": "execution-providers:CPUExecutionProvider",
            "device": "cpu",
        },
        **shared,
    }
    on_dml = {
        "runtime": {
            "name": "onnxruntime",
            "backend": "execution-providers:DmlExecutionProvider,CPUExecutionProvider",
            "device": "dml",
        },
        **shared,
    }
    assert compare_classification(on_cpu, on_dml)["classification"] == "NOT_COMPARABLE"
