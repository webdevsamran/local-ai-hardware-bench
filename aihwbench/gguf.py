"""Read model identity out of a GGUF file's header.

Every llama.cpp result this project published carried `quantization: null` and
`parameters: null`, for files whose names say `q4_k_m` and whose headers say
so properly. `model.quantization` is in the comparison-safety classifier's
strict set, and `_same(None, None)` is True by design, so null on both sides
meant two results at different quantizations *agreed* about it.

The filename is not the answer. `model.gguf` is a legal name for any
quantization, files get renamed, and a wrong quantization is worse than a
missing one because it makes two different models compare as one. The header
is authoritative and costs one read of the first few kilobytes.

Only the header is parsed -- never the tensor data -- so this is bounded work
on a file that may be tens of gigabytes.

Format (GGUF v2/v3): a magic, a version, tensor and metadata counts, then
metadata key/value pairs. Values are typed, and an unknown type ends the
parse rather than guessing at a length and reading garbage.
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Any, BinaryIO

__all__ = ["read_gguf_identity", "GGUF_MAGIC", "FILE_TYPES"]

GGUF_MAGIC = b"GGUF"

#: Cap on metadata pairs read, so a corrupt or hostile count cannot make this
#: loop for a long time on a file we only wanted four fields from.
_MAX_KV = 4096

#: Cap on a single string, for the same reason. Real metadata strings are
#: chat templates at the largest, comfortably under this.
_MAX_STRING = 8 * 1024 * 1024

# GGUF value type tags.
_UINT8, _INT8, _UINT16, _INT16, _UINT32, _INT32 = 0, 1, 2, 3, 4, 5
_FLOAT32, _BOOL, _STRING, _ARRAY, _UINT64, _INT64, _FLOAT64 = 6, 7, 8, 9, 10, 11, 12

_SCALARS: dict[int, tuple[str, int]] = {
    _UINT8: ("<B", 1),
    _INT8: ("<b", 1),
    _UINT16: ("<H", 2),
    _INT16: ("<h", 2),
    _UINT32: ("<I", 4),
    _INT32: ("<i", 4),
    _FLOAT32: ("<f", 4),
    _BOOL: ("<?", 1),
    _UINT64: ("<Q", 8),
    _INT64: ("<q", 8),
    _FLOAT64: ("<d", 8),
}

#: `general.file_type` values, from ggml's `llama_ftype`. Named as the
#: ecosystem names them, lower-cased to match the vocabulary the fit estimator
#: and the dashboard filter already use.
#:
#: Deliberately not exhaustive: a value not listed here yields None rather
#: than a guess, because an invented quantization label would be exactly the
#: confident wrong answer this module exists to avoid.
FILE_TYPES: dict[int, str] = {
    0: "f32",
    1: "f16",
    2: "q4_0",
    3: "q4_1",
    7: "q8_0",
    8: "q5_0",
    9: "q5_1",
    10: "q2_k",
    11: "q3_k_s",
    12: "q3_k_m",
    13: "q3_k_l",
    14: "q4_k_s",
    15: "q4_k_m",
    16: "q5_k_s",
    17: "q5_k_m",
    18: "q6_k",
    19: "iq2_xxs",
    20: "iq2_xs",
    21: "q2_k_s",
    22: "iq3_xs",
    23: "iq3_xxs",
    24: "iq1_s",
    25: "iq4_nl",
    26: "iq3_s",
    27: "iq3_m",
    28: "iq2_s",
    29: "iq2_m",
    30: "iq4_xs",
    31: "iq1_m",
    32: "bf16",
    36: "tq1_0",
    37: "tq2_0",
}


def _read(handle: BinaryIO, size: int) -> bytes:
    data = handle.read(size)
    if len(data) != size:
        raise ValueError("truncated GGUF header")
    return data


def _read_scalar(handle: BinaryIO, value_type: int) -> Any:
    fmt, size = _SCALARS[value_type]
    return struct.unpack(fmt, _read(handle, size))[0]


def _read_string(handle: BinaryIO) -> str:
    (length,) = struct.unpack("<Q", _read(handle, 8))
    if length > _MAX_STRING:
        raise ValueError(f"implausible GGUF string length: {length}")
    return _read(handle, length).decode("utf-8", errors="replace")


def _read_value(handle: BinaryIO, value_type: int) -> Any:
    if value_type in _SCALARS:
        return _read_scalar(handle, value_type)
    if value_type == _STRING:
        return _read_string(handle)
    if value_type == _ARRAY:
        (item_type,) = struct.unpack("<I", _read(handle, 4))
        (count,) = struct.unpack("<Q", _read(handle, 8))
        # Arrays are skipped rather than collected: the only one that matters
        # here is the tokenizer vocabulary, which is large and not wanted.
        # Skipping still has to walk it, because entries are variable-width.
        for _ in range(count):
            _read_value(handle, item_type)
        return None
    raise ValueError(f"unknown GGUF value type: {value_type}")


def read_gguf_header(path: str | Path, *, wanted: set[str] | None = None) -> dict[str, Any]:
    """Metadata key/value pairs from a GGUF header.

    Stops early once every key in ``wanted`` has been seen, so the common case
    reads a few kilobytes rather than walking a large tokenizer vocabulary.

    Returns an empty mapping for a file that is not GGUF or whose header
    cannot be parsed. A header this cannot read is one this must not guess
    about.
    """
    metadata: dict[str, Any] = {}
    try:
        with open(path, "rb") as handle:
            if _read(handle, 4) != GGUF_MAGIC:
                return {}
            (version,) = struct.unpack("<I", _read(handle, 4))
            if version not in (2, 3):
                # v1 laid out its counts differently. Refusing is better than
                # reading the wrong offsets and reporting whatever appears.
                return {}
            _read(handle, 8)  # tensor count, not needed
            (kv_count,) = struct.unpack("<Q", _read(handle, 8))
            if kv_count > _MAX_KV:
                return {}

            for _ in range(kv_count):
                key = _read_string(handle)
                (value_type,) = struct.unpack("<I", _read(handle, 4))
                metadata[key] = _read_value(handle, value_type)
                if wanted and wanted <= set(metadata):
                    break
    except (OSError, ValueError, struct.error, UnicodeDecodeError):
        return {}
    return metadata


def read_gguf_identity(path: str | Path) -> dict[str, Any]:
    """Model identity from a GGUF header, for a result's `model` block.

    Every field is null when the header does not state it. Nothing is derived
    from the filename: `model.gguf` is a legal name for any quantization, and
    a wrong quantization makes two different models compare as one.
    """
    wanted = {
        "general.architecture",
        "general.file_type",
        "general.name",
        "general.size_label",
    }
    metadata = read_gguf_header(path, wanted=wanted)
    if not metadata:
        return {"quantization": None, "parameters": None, "family": None}

    file_type = metadata.get("general.file_type")
    quantization = FILE_TYPES.get(int(file_type)) if isinstance(file_type, int) else None

    # `general.size_label` is the ecosystem's own parameter-count label
    # ("0.5B", "7B"), and is what `analysis.fit` already knows how to parse.
    size_label = metadata.get("general.size_label")
    architecture = metadata.get("general.architecture")

    return {
        "quantization": quantization,
        "parameters": size_label if isinstance(size_label, str) else None,
        "family": architecture if isinstance(architecture, str) else None,
    }
