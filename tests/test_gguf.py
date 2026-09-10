"""Reading model identity out of a GGUF header.

Every llama.cpp result this project published carried `quantization: null` and
`parameters: null`, for a file whose header states both. `model.quantization`
is in the comparison-safety classifier's strict set and `_same(None, None)` is
True, so null on both sides meant two runs at different quantizations agreed
about it.

This parses a binary format from files that may be tens of gigabytes, so the
tests below care as much about what it refuses as about what it reads: a
truncated or hostile header must yield nothing rather than whatever happens to
sit at the offset it guessed.
"""

from __future__ import annotations

import struct
from pathlib import Path

from aihwbench.gguf import FILE_TYPES, GGUF_MAGIC, read_gguf_header, read_gguf_identity

_UINT32, _STRING, _ARRAY = 4, 8, 9


def _kv_string(key: str, value: str) -> bytes:
    key_b = key.encode("utf-8")
    val_b = value.encode("utf-8")
    return (
        struct.pack("<Q", len(key_b))
        + key_b
        + struct.pack("<I", _STRING)
        + struct.pack("<Q", len(val_b))
        + val_b
    )


def _kv_uint32(key: str, value: int) -> bytes:
    key_b = key.encode("utf-8")
    return (
        struct.pack("<Q", len(key_b))
        + key_b
        + struct.pack("<I", _UINT32)
        + struct.pack("<I", value)
    )


def _gguf(pairs: bytes, *, count: int, version: int = 3, magic: bytes = GGUF_MAGIC) -> bytes:
    return (
        magic
        + struct.pack("<I", version)
        + struct.pack("<Q", 0)  # tensor count
        + struct.pack("<Q", count)
        + pairs
    )


def _write(tmp_path: Path, data: bytes, name: str = "m.gguf") -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path


def test_reads_quantization_architecture_and_size(tmp_path):
    pairs = (
        _kv_string("general.architecture", "qwen2")
        + _kv_string("general.size_label", "0.5B")
        + _kv_uint32("general.file_type", 15)  # q4_k_m
    )
    path = _write(tmp_path, _gguf(pairs, count=3))

    identity = read_gguf_identity(path)
    assert identity == {"quantization": "q4_k_m", "parameters": "0.5B", "family": "qwen2"}


def test_an_unknown_file_type_yields_no_quantization(tmp_path):
    """A label this does not know is a label it must not invent.

    An invented quantization is worse than a missing one: it makes two
    different models compare as one.
    """
    unknown = max(FILE_TYPES) + 500
    pairs = _kv_uint32("general.file_type", unknown)
    path = _write(tmp_path, _gguf(pairs, count=1))

    assert read_gguf_identity(path)["quantization"] is None


def test_a_file_that_is_not_gguf_yields_nothing(tmp_path):
    path = _write(tmp_path, b"NOTGGUF" + b"\x00" * 64)
    assert read_gguf_header(path) == {}
    assert read_gguf_identity(path) == {
        "quantization": None,
        "parameters": None,
        "family": None,
    }


def test_a_truncated_header_yields_nothing(tmp_path):
    """Declaring three pairs and supplying one must not return the one.

    A partial parse of a binary format is how a reader ends up reporting
    whatever bytes followed.
    """
    pairs = _kv_string("general.architecture", "qwen2")
    path = _write(tmp_path, _gguf(pairs, count=3))
    assert read_gguf_header(path) == {}


def test_an_unsupported_version_is_refused(tmp_path):
    """v1 laid out its counts differently; reading it as v3 reads garbage."""
    pairs = _kv_string("general.architecture", "qwen2")
    path = _write(tmp_path, _gguf(pairs, count=1, version=1))
    assert read_gguf_header(path) == {}


def test_an_implausible_pair_count_is_refused(tmp_path):
    """A corrupt count must not become a long loop over a huge file."""
    path = _write(tmp_path, _gguf(b"", count=2**40))
    assert read_gguf_header(path) == {}


def test_an_implausible_string_length_is_refused(tmp_path):
    header = (
        GGUF_MAGIC
        + struct.pack("<I", 3)
        + struct.pack("<Q", 0)
        + struct.pack("<Q", 1)
        + struct.pack("<Q", 2**40)  # key length
    )
    assert read_gguf_header(_write(tmp_path, header)) == {}


def test_an_unknown_value_type_stops_the_parse(tmp_path):
    """Skipping an unknown type means guessing its width."""
    key = b"general.mystery"
    pairs = struct.pack("<Q", len(key)) + key + struct.pack("<I", 999)
    path = _write(tmp_path, _gguf(pairs, count=1))
    assert read_gguf_header(path) == {}


def test_arrays_are_walked_not_collected(tmp_path):
    """The tokenizer vocabulary is an array, and it is not wanted.

    It still has to be walked, because entries are variable-width and the
    keys after it cannot be reached otherwise.
    """
    key = b"tokenizer.ggml.tokens"
    items = b"".join(struct.pack("<Q", len(tok)) + tok for tok in (b"a", b"bb", b"ccc"))
    array = (
        struct.pack("<Q", len(key))
        + key
        + struct.pack("<I", _ARRAY)
        + struct.pack("<I", _STRING)
        + struct.pack("<Q", 3)
        + items
    )
    pairs = array + _kv_string("general.architecture", "llama")
    path = _write(tmp_path, _gguf(pairs, count=2))

    metadata = read_gguf_header(path)
    assert metadata["tokenizer.ggml.tokens"] is None  # walked, not kept
    assert metadata["general.architecture"] == "llama"


def test_a_missing_file_yields_nothing(tmp_path):
    assert read_gguf_identity(tmp_path / "absent.gguf") == {
        "quantization": None,
        "parameters": None,
        "family": None,
    }


def test_identity_is_never_taken_from_the_filename(tmp_path):
    """`model.gguf` is a legal name for any quantization, and files get renamed."""
    path = _write(tmp_path, _gguf(b"", count=0), name="qwen2.5-0.5b-instruct-q4_k_m.gguf")
    assert read_gguf_identity(path)["quantization"] is None
