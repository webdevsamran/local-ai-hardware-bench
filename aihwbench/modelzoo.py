"""The model zoo: what was benchmarked, under what licence, and how to get it.

A benchmark result names a model. That name is not enough to obtain the model,
not enough to verify you obtained the *same* model, and says nothing about
whether you are allowed to redistribute it. This module holds the manifest
that supplies all three.

Two problems in this repository's own corpus motivated it.

**An artifact went missing.** Four published results measure
`mobilenetv2-12.onnx`. The file is no longer on the machine that produced
them, no result records where it came from, and all four record
`checksum: null`. Nobody can obtain that model, and nobody can confirm that a
file they *did* obtain is the one that was measured. The measurements survive;
the thing measured does not.

**Two checksums of the same weights disagree.** The llama.cpp results record
`sha256:c5396e06...`, the SHA-256 of the GGUF weights file. The Ollama results
record `a8b0c515...`, which is Ollama's manifest digest -- a hash of a document
listing the weights layer *and* the template *and* the system prompt. The two
runs used byte-identical weights. Nothing in the corpus says so, because the
field holds two different kinds of hash and does not say which.

`model.checksum` is in the comparison-safety classifier's strict set, so this
errs safely: the mismatch pushes a pair toward NOT_COMPARABLE rather than
falsely toward agreement. But "cannot tell" is recorded as "differs", and the
zoo is where the distinction is written down instead.

Licences are read from the artifact, never inferred.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = [
    "ZooEntry",
    "ZooError",
    "load_zoo",
    "verify_entry",
    "fetch_entry",
    "entry_for_checksum",
    "CHECKSUM_KINDS",
    "LICENSE_SOURCES",
    "DEFAULT_ZOO_PATH",
]


class ZooError(ValueError):
    """Raised when a zoo manifest is malformed or self-inconsistent."""


#: What a recorded checksum is a hash *of*. The corpus proves this cannot be
#: left implicit: two of these appear in published results under one field.
CHECKSUM_KINDS = {
    # SHA-256 of the weights file itself (a .gguf, a .onnx). Identifies the
    # weights and nothing else, so it is the only kind comparable across
    # runtimes.
    "weights-sha256",
    # SHA-256 of an Ollama manifest: weights layer + template + system prompt
    # + licence layer. Changes when the template changes and the weights do
    # not, so it is an identity for a *served configuration*, not for weights.
    "ollama-manifest-sha256",
}

#: Where a licence statement came from. A licence is a claim about someone
#: else's legal terms, so the provenance of the claim is recorded with it.
LICENSE_SOURCES = {
    # The GGUF header's `general.license`. Written by the publisher, travels
    # with the file, re-derivable by anyone holding it.
    "gguf-header",
    # Ollama's `/api/show`. Also the publisher's, relayed by the runtime.
    "ollama-api",
    # A human wrote it into the manifest. Recorded as such, because a human
    # can be wrong and a header cannot be re-read to check a format that
    # carries no licence field at all.
    "declared",
}

DEFAULT_ZOO_PATH = Path("models") / "zoo.json"

_SHA256_RE = re.compile(r"\b(?:sha256[:-])?([0-9a-f]{64})\b")

_ALLOWED_KEYS = {
    "key",
    "name",
    "format",
    "family",
    "parameters",
    "quantization",
    "license",
    "license_link",
    "license_source",
    "checksum",
    "checksum_kind",
    "aliases",
    "source",
    "size_bytes",
    "notes",
}

_ALLOWED_SOURCE_KEYS = {"kind", "ref", "url"}
_SOURCE_KINDS = {"ollama", "https", "unavailable"}


@dataclass(frozen=True)
class ZooEntry:
    """One obtainable, verifiable, licensed model."""

    key: str
    name: str
    format: str
    source: dict[str, Any]
    license: str | None = None
    license_link: str | None = None
    license_source: str | None = None
    checksum: str | None = None
    checksum_kind: str | None = None
    family: str | None = None
    parameters: str | None = None
    quantization: str | None = None
    size_bytes: int | None = None
    notes: str | None = None
    #: Other checksum strings, of other kinds, that denote this same model.
    #: This is how the corpus's llama.cpp and Ollama results are tied to one
    #: entry despite recording different hashes of different things.
    aliases: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "name": self.name,
            "format": self.format,
            "family": self.family,
            "parameters": self.parameters,
            "quantization": self.quantization,
            "license": self.license,
            "license_link": self.license_link,
            "license_source": self.license_source,
            "checksum": self.checksum,
            "checksum_kind": self.checksum_kind,
            "aliases": list(self.aliases),
            "source": dict(self.source),
            "size_bytes": self.size_bytes,
            "notes": self.notes,
        }

    @property
    def obtainable(self) -> bool:
        """Whether the manifest states any way to get this model."""
        return self.source.get("kind") in {"ollama", "https"}


def _normalized_digest(value: str | None) -> str | None:
    """The bare 64-hex digest inside a checksum string, if there is one.

    Accepts `sha256:<hex>`, `sha256-<hex>` and bare `<hex>`, because all three
    spellings occur: published results use the first and third, and Ollama
    names blob files with the second.
    """
    if not isinstance(value, str):
        return None
    match = _SHA256_RE.search(value.strip().lower())
    return match.group(1) if match else None


def _parse_entry(data: Any, index: int, source_name: str) -> ZooEntry:
    where = f"{source_name} entry {index}"
    if not isinstance(data, dict):
        raise ZooError(f"{where}: expected an object, got {type(data).__name__}")

    unknown = set(data) - _ALLOWED_KEYS
    if unknown:
        raise ZooError(f"{where}: unknown key(s) {sorted(unknown)}")

    for required in ("key", "name", "format"):
        if not isinstance(data.get(required), str) or not data[required]:
            raise ZooError(f"{where}: {required!r} is required and must be a non-empty string")

    raw_source = data.get("source")
    if not isinstance(raw_source, dict):
        raise ZooError(f"{where}: 'source' is required and must be an object")
    unknown_source = set(raw_source) - _ALLOWED_SOURCE_KEYS
    if unknown_source:
        raise ZooError(f"{where}: unknown source key(s) {sorted(unknown_source)}")
    kind = raw_source.get("kind")
    if kind not in _SOURCE_KINDS:
        raise ZooError(f"{where}: source.kind must be one of {sorted(_SOURCE_KINDS)}, got {kind!r}")
    if kind == "https":
        url = raw_source.get("url")
        if not isinstance(url, str) or not url.startswith("https://"):
            raise ZooError(f"{where}: an https source needs an https:// url")
    if kind == "ollama" and not isinstance(raw_source.get("ref"), str):
        raise ZooError(f"{where}: an ollama source needs a 'ref' to pull")

    checksum = data.get("checksum")
    checksum_kind = data.get("checksum_kind")
    if checksum is not None and checksum_kind not in CHECKSUM_KINDS:
        raise ZooError(
            f"{where}: checksum_kind must be one of {sorted(CHECKSUM_KINDS)} "
            f"when a checksum is recorded, got {checksum_kind!r}. A hash whose "
            "basis is unstated cannot be compared with another hash."
        )
    if checksum is not None and _normalized_digest(checksum) is None:
        raise ZooError(f"{where}: checksum {checksum!r} is not a SHA-256 digest")

    license_value = data.get("license")
    license_source = data.get("license_source")
    if license_value is not None and license_source not in LICENSE_SOURCES:
        raise ZooError(
            f"{where}: license_source must be one of {sorted(LICENSE_SOURCES)} "
            f"when a licence is recorded, got {license_source!r}. An unattributed "
            "licence claim cannot be checked against the artifact."
        )

    aliases = data.get("aliases") or []
    if not isinstance(aliases, list) or not all(isinstance(a, str) for a in aliases):
        raise ZooError(f"{where}: 'aliases' must be a list of strings")

    return ZooEntry(
        key=data["key"],
        name=data["name"],
        format=data["format"],
        source=dict(raw_source),
        license=license_value,
        license_link=data.get("license_link"),
        license_source=license_source,
        checksum=checksum,
        checksum_kind=checksum_kind,
        family=data.get("family"),
        parameters=data.get("parameters"),
        quantization=data.get("quantization"),
        size_bytes=data.get("size_bytes"),
        notes=data.get("notes"),
        aliases=tuple(aliases),
    )


def load_zoo(path: str | Path | None = None) -> list[ZooEntry]:
    """Read and validate the model zoo manifest.

    Unknown keys are rejected rather than ignored, for the reason experiment
    manifests reject them: a typo that silently changes nothing is worse than
    one that fails.
    """
    target = Path(path) if path is not None else DEFAULT_ZOO_PATH
    try:
        raw = json.loads(Path(target).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ZooError(f"no model zoo manifest at {target}") from exc
    except json.JSONDecodeError as exc:
        raise ZooError(f"{target} is not valid JSON: {exc}") from exc

    models = raw.get("models") if isinstance(raw, dict) else None
    if not isinstance(models, list):
        raise ZooError(f"{target}: expected a top-level object with a 'models' list")

    entries = [_parse_entry(item, i, str(target)) for i, item in enumerate(models)]

    seen: dict[str, int] = {}
    for i, entry in enumerate(entries):
        if entry.key in seen:
            raise ZooError(
                f"{target}: duplicate key {entry.key!r} (entries {seen[entry.key]}, {i})"
            )
        seen[entry.key] = i
    return entries


def entry_for_checksum(entries: list[ZooEntry], checksum: str | None) -> ZooEntry | None:
    """The zoo entry a result's `model.checksum` refers to, if any.

    Matches the entry's own checksum and its aliases, so a result recording an
    Ollama manifest digest and one recording the weights digest both resolve
    to the single model they measured.
    """
    digest = _normalized_digest(checksum)
    if digest is None:
        return None
    for entry in entries:
        candidates = {_normalized_digest(entry.checksum)} | {
            _normalized_digest(a) for a in entry.aliases
        }
        if digest in candidates:
            return entry
    return None


def _hash_file(path: Path) -> str | None:
    """Streaming SHA-256 of a file, or None if it cannot be read."""
    import hashlib

    digest = hashlib.sha256()
    try:
        with open(path, "rb") as handle:
            while chunk := handle.read(1 << 20):
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def _license_from_artifact(entry: ZooEntry, path: Path | None) -> dict[str, Any]:
    """Re-read the licence from the artifact, for comparison with the manifest."""
    if path is not None and entry.format == "gguf":
        from .gguf import read_gguf_license

        return read_gguf_license(path)
    if entry.source.get("kind") == "ollama":
        from .backends.ollama import model_license

        return model_license(str(entry.source.get("ref")))
    return {"license": None, "license_link": None}


def verify_entry(entry: ZooEntry, path: str | Path | None = None) -> dict[str, Any]:
    """Check that an entry describes something obtainable and unchanged.

    Three outcomes, and the distinction between the last two matters:

    - ``verified: True``  -- the artifact was found and its hash matches.
    - ``verified: False`` -- it was found and its hash does *not* match. The
      file is not the one that was benchmarked.
    - ``verified: None``  -- it could not be checked at all. Not a pass.

    Passing ``path`` hashes that file. Otherwise an Ollama entry is checked
    against the running server, which reports the weights digest without
    anybody having to know where Ollama keeps its blobs.
    """
    report: dict[str, Any] = {
        "key": entry.key,
        "obtainable": entry.obtainable,
        "verified": None,
        "checksum_expected": entry.checksum,
        "checksum_kind": entry.checksum_kind,
        "checksum_actual": None,
        "license_recorded": entry.license,
        "license_source": entry.license_source,
        "license_matches": None,
        "reason": "",
    }

    if entry.checksum is None:
        report["reason"] = (
            "no checksum is recorded, so no file can be confirmed to be the "
            "one that was benchmarked"
        )
        return report

    expected = _normalized_digest(entry.checksum)
    actual: str | None = None
    resolved: Path | None = None

    if path is not None:
        resolved = Path(path)
        if not resolved.is_file():
            report["reason"] = f"{resolved} does not exist"
            return report
        if entry.checksum_kind != "weights-sha256":
            report["reason"] = (
                f"this entry records a {entry.checksum_kind}, which is not a hash "
                "of the weights file, so hashing a file cannot confirm it"
            )
            return report
        actual = _hash_file(resolved)
    elif entry.source.get("kind") == "ollama":
        from .backends.ollama import model_digest, model_weights_digest

        ref = str(entry.source.get("ref"))
        actual = (
            model_weights_digest(ref)
            if entry.checksum_kind == "weights-sha256"
            else _normalized_digest(model_digest(ref))
        )
        if actual is None:
            report["reason"] = (
                f"Ollama did not report a digest for {ref}: it is not installed, "
                "or the server is not running"
            )
            return report
    else:
        report["reason"] = (
            "nothing local to check: pass a path to the downloaded artifact, "
            f"or obtain it from {entry.source.get('url') or entry.source.get('kind')}"
        )
        return report

    report["checksum_actual"] = actual
    report["verified"] = actual == expected
    report["reason"] = (
        "matches the recorded checksum"
        if report["verified"]
        else f"expected {expected}, got {actual}: this is not the model that was benchmarked"
    )

    stated = _license_from_artifact(entry, resolved)
    if stated.get("license") is not None:
        report["license_stated_by_artifact"] = stated["license"]
        report["license_matches"] = stated["license"] == entry.license
        if not report["license_matches"]:
            report["reason"] += (
                f"; the artifact states licence {stated['license']!r} but the "
                f"manifest records {entry.license!r}"
            )
    return report


def fetch_entry(
    entry: ZooEntry,
    dest_dir: str | Path = "models",
    *,
    on_progress: Any = None,
) -> dict[str, Any]:
    """Obtain a model, and refuse to keep one that is not the right model.

    A download helper that does not verify is a way to benchmark a different
    model than the one you meant to. So the hash is computed while the bytes
    arrive, and a file whose hash does not match the manifest is deleted
    rather than left on disk where something could pick it up.

    An entry with no recorded checksum still downloads, and the report says
    plainly that nothing was verified and gives the hash that was observed, so
    a maintainer can record it after checking it against the publisher.
    """
    import hashlib
    import shutil
    import tempfile
    import urllib.request

    kind = entry.source.get("kind")
    if kind == "ollama":
        from .backends.base import run_command

        ref = str(entry.source.get("ref"))
        code, out = run_command(["ollama", "pull", ref], timeout=3600.0)
        report = verify_entry(entry)
        report["fetched"] = code == 0
        if code != 0:
            report["reason"] = f"ollama pull {ref} failed: {out or 'no output'}"
        return report

    if kind != "https":
        return {
            "key": entry.key,
            "fetched": False,
            "verified": None,
            "reason": (f"this entry records no way to obtain the model (source.kind is {kind!r})"),
        }

    url = str(entry.source.get("url"))
    if not url.startswith("https://"):
        raise ZooError(f"{entry.key}: refusing to fetch a non-https url")

    destination = Path(dest_dir) / f"{entry.key}.{entry.format}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    written = 0

    request = urllib.request.Request(url, headers={"User-Agent": "aihwbench"})
    handle = tempfile.NamedTemporaryFile(delete=False, dir=destination.parent, suffix=".part")
    temporary = Path(handle.name)
    try:
        with urllib.request.urlopen(request, timeout=120) as response, handle:
            while chunk := response.read(1 << 20):
                digest.update(chunk)
                handle.write(chunk)
                written += len(chunk)
                if on_progress is not None:
                    on_progress(written)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise

    observed = digest.hexdigest()
    expected = _normalized_digest(entry.checksum)

    if expected is not None and observed != expected:
        temporary.unlink(missing_ok=True)
        return {
            "key": entry.key,
            "fetched": False,
            "verified": False,
            "checksum_expected": expected,
            "checksum_actual": observed,
            "reason": (
                f"downloaded {written} bytes from {url} whose SHA-256 is {observed}, "
                f"but the manifest records {expected}. The file has been deleted: "
                "it is not the model that was benchmarked."
            ),
        }

    shutil.move(str(temporary), str(destination))
    return {
        "key": entry.key,
        "fetched": True,
        "path": str(destination),
        "bytes": written,
        # None, not False: False is the claim "this is the wrong model", and
        # an entry with no recorded checksum was not checked at all.
        "verified": True if expected is not None else None,
        "checksum_actual": observed,
        "reason": (
            "downloaded and the SHA-256 matches the manifest"
            if expected is not None
            else (
                "downloaded, but the manifest records no checksum, so nothing was "
                f"verified. Observed SHA-256: {observed}"
            )
        ),
    }
