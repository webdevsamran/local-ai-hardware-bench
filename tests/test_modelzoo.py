"""The model zoo records what was benchmarked, well enough to get it again.

Two facts from this repository's own corpus set the requirements.

Four published results measure `mobilenetv2-12.onnx`. The file was not on the
machine any more, nothing recorded where it came from, and all four record
`checksum: null`. The measurements outlived the thing measured.

And the llama.cpp results record `sha256:c5396e06...` while the Ollama results
record `a8b0c515...` for byte-identical weights -- because the first hashes the
weights file and the second hashes Ollama's manifest, which also covers the
template and the system prompt. One field, two kinds of hash, no way to tell
which. `model.checksum` is in the classifier's strict set, so the disagreement
pushes a pair toward NOT_COMPARABLE rather than falsely toward agreement; the
zoo is where "these are in fact the same weights" gets written down.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from aihwbench.modelzoo import (
    CHECKSUM_KINDS,
    LICENSE_SOURCES,
    ZooEntry,
    ZooError,
    entry_for_checksum,
    fetch_entry,
    load_zoo,
    verify_entry,
)

ZOO = Path("models/zoo.json")


def _entry(**overrides: object) -> dict:
    base = {
        "key": "m1",
        "name": "Model One",
        "format": "gguf",
        "source": {"kind": "ollama", "ref": "m1:latest"},
        "checksum": "sha256:" + "a" * 64,
        "checksum_kind": "weights-sha256",
        "license": "apache-2.0",
        "license_source": "gguf-header",
    }
    base.update(overrides)
    return base


def _write(tmp_path: Path, *entries: dict) -> Path:
    path = tmp_path / "zoo.json"
    path.write_text(json.dumps({"models": list(entries)}), encoding="utf-8")
    return path


# --- the manifest refuses to be vague ------------------------------------


def test_a_checksum_without_a_kind_is_rejected(tmp_path):
    """The corpus's exact failure: a hash whose basis nobody stated.

    Two published results hash different things under one field name. A
    manifest that allowed the same would reproduce the problem it exists to
    record.
    """
    path = _write(tmp_path, _entry(checksum_kind=None))
    with pytest.raises(ZooError, match="checksum_kind must be one of"):
        load_zoo(path)


def test_an_unattributed_licence_is_rejected(tmp_path):
    """A licence is a claim about someone else's terms.

    Recorded without saying who said it, it cannot be checked against the
    artifact and cannot be argued with.
    """
    path = _write(tmp_path, _entry(license_source=None))
    with pytest.raises(ZooError, match="license_source must be one of"):
        load_zoo(path)


def test_a_checksum_that_is_not_a_digest_is_rejected(tmp_path):
    path = _write(tmp_path, _entry(checksum="probably-fine"))
    with pytest.raises(ZooError, match="not a SHA-256 digest"):
        load_zoo(path)


def test_unknown_keys_fail_rather_than_being_ignored(tmp_path):
    """Same rule experiment manifests use: a silent typo is the worse bug."""
    path = _write(tmp_path, _entry(licence="apache-2.0"))
    with pytest.raises(ZooError, match="unknown key"):
        load_zoo(path)


def test_duplicate_keys_are_rejected(tmp_path):
    path = _write(tmp_path, _entry(), _entry())
    with pytest.raises(ZooError, match="duplicate key"):
        load_zoo(path)


def test_a_non_https_source_is_rejected(tmp_path):
    path = _write(tmp_path, _entry(source={"kind": "https", "url": "http://example.com/m.gguf"}))
    with pytest.raises(ZooError, match="https:// url"):
        load_zoo(path)


def test_a_missing_manifest_says_so(tmp_path):
    with pytest.raises(ZooError, match="no model zoo manifest"):
        load_zoo(tmp_path / "absent.json")


# --- verification distinguishes three outcomes ---------------------------


def test_a_matching_file_verifies(tmp_path):
    blob = tmp_path / "weights.gguf"
    blob.write_bytes(b"some weights")
    digest = hashlib.sha256(b"some weights").hexdigest()
    path = _write(
        tmp_path,
        _entry(checksum=f"sha256:{digest}", source={"kind": "https", "url": "https://e/w.gguf"}),
    )
    report = verify_entry(load_zoo(path)[0], blob)
    assert report["verified"] is True


def test_a_different_file_is_a_mismatch_not_a_pass(tmp_path):
    blob = tmp_path / "weights.gguf"
    blob.write_bytes(b"different weights")
    path = _write(tmp_path, _entry(source={"kind": "https", "url": "https://e/w.gguf"}))
    report = verify_entry(load_zoo(path)[0], blob)
    assert report["verified"] is False
    assert "not the model that was benchmarked" in report["reason"]


def test_unverifiable_is_none_and_never_false(tmp_path):
    """`None` and `False` are different claims and must not be confused.

    `False` says "this is the wrong model". Nothing was checked here, and
    reporting that as a mismatch would condemn a file nobody looked at.
    """
    path = _write(tmp_path, _entry(checksum=None, checksum_kind=None))
    report = verify_entry(load_zoo(path)[0])
    assert report["verified"] is None
    assert "no checksum is recorded" in report["reason"]


def test_hashing_a_file_cannot_confirm_a_manifest_digest(tmp_path):
    """An Ollama manifest digest is not a hash of the weights file.

    Hashing the weights and comparing against it would always mismatch, which
    would read as "wrong model" when the real answer is "wrong question".
    """
    blob = tmp_path / "weights.gguf"
    blob.write_bytes(b"w")
    path = _write(tmp_path, _entry(checksum_kind="ollama-manifest-sha256"))
    report = verify_entry(load_zoo(path)[0], blob)
    assert report["verified"] is None
    assert "not a hash of the weights file" in report["reason"]


def test_a_missing_path_is_reported_not_crashed(tmp_path):
    path = _write(tmp_path, _entry(source={"kind": "https", "url": "https://e/w.gguf"}))
    report = verify_entry(load_zoo(path)[0], tmp_path / "gone.gguf")
    assert report["verified"] is None
    assert "does not exist" in report["reason"]


def test_a_licence_the_artifact_contradicts_is_caught(tmp_path, monkeypatch):
    """The failure mode a hand-written licence field actually has."""
    import aihwbench.modelzoo as modelzoo

    blob = tmp_path / "weights.gguf"
    blob.write_bytes(b"w")
    digest = hashlib.sha256(b"w").hexdigest()
    monkeypatch.setattr(
        modelzoo,
        "_license_from_artifact",
        lambda entry, path: {"license": "apache-2.0", "license_link": None},
    )
    path = _write(tmp_path, _entry(checksum=f"sha256:{digest}", license="MIT"))
    report = verify_entry(load_zoo(path)[0], blob)
    assert report["verified"] is True
    assert report["license_matches"] is False
    assert "but the manifest records 'MIT'" in report["reason"]


# --- the download helper refuses to keep the wrong model -----------------


def test_a_download_that_does_not_match_is_deleted(tmp_path, monkeypatch):
    """A helper that downloads without verifying is a way to benchmark the
    wrong model without noticing."""
    import io
    import urllib.request

    class _Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _Response(b"wrong bytes"))
    path = _write(tmp_path, _entry(source={"kind": "https", "url": "https://e/w.gguf"}))
    report = fetch_entry(load_zoo(path)[0], tmp_path / "dest")
    assert report["fetched"] is False
    assert report["verified"] is False
    assert not list((tmp_path / "dest").glob("*.gguf"))
    assert not list((tmp_path / "dest").glob("*.part"))


def test_a_download_with_no_recorded_checksum_is_unverified_not_verified(tmp_path, monkeypatch):
    """Found while building this: the helper reported `verified: False`.

    That is the claim "this is the wrong model" for a file nothing checked.
    """
    import io
    import urllib.request

    class _Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _Response(b"bytes"))
    path = _write(
        tmp_path,
        _entry(checksum=None, checksum_kind=None, source={"kind": "https", "url": "https://e/w"}),
    )
    report = fetch_entry(load_zoo(path)[0], tmp_path / "dest")
    assert report["fetched"] is True
    assert report["verified"] is None
    assert hashlib.sha256(b"bytes").hexdigest() in report["reason"]


def test_an_unobtainable_entry_is_not_fetched(tmp_path):
    path = _write(tmp_path, _entry(source={"kind": "unavailable"}))
    report = fetch_entry(load_zoo(path)[0], tmp_path)
    assert report["fetched"] is False
    assert "no way to obtain" in report["reason"]


# --- aliases tie the corpus's two checksum kinds to one model ------------


def test_both_checksum_kinds_resolve_to_the_same_model(tmp_path):
    weights = "c" * 64
    manifest = "a" * 64
    path = _write(
        tmp_path,
        _entry(checksum=f"sha256:{weights}", aliases=[manifest]),
    )
    entries = load_zoo(path)
    assert entry_for_checksum(entries, f"sha256:{weights}").key == "m1"
    assert entry_for_checksum(entries, manifest).key == "m1"
    assert entry_for_checksum(entries, "d" * 64) is None
    assert entry_for_checksum(entries, None) is None


def test_the_repository_manifest_ties_its_own_published_results_together():
    """The llama.cpp and Ollama results must resolve to one model.

    This is the concrete payoff: before the zoo, the corpus held two
    unrelated-looking hashes for one set of weights.
    """
    entries = load_zoo(ZOO)
    llama_cpp = "sha256:c5396e06af294bd101b30dce59131a76d2b773e76950acc870eda801d3ab0515"
    ollama = "a8b0c51577010a279d933d14c2a8ab4b268079d44c5c8830c0a93900f1827c67"
    resolved = entry_for_checksum(entries, llama_cpp)
    assert resolved is not None
    assert entry_for_checksum(entries, ollama) is resolved


# --- the shipped manifest stays honest -----------------------------------


def test_the_repository_manifest_loads():
    assert load_zoo(ZOO)


def _slug(value: str) -> str:
    """Collapse the separators that differ between a tag and a filename.

    `qwen2.5:0.5b-instruct-q4_K_M` and `qwen2.5-0.5b-instruct-q4_k_m.gguf`
    name one model. Only the separators and the extension differ.
    """
    stem = value.rsplit(".gguf", 1)[0].rsplit(".onnx", 1)[0].lower()
    return "".join(c for c in stem if c.isalnum())


def test_every_model_the_corpus_measured_is_in_the_zoo():
    """A published result naming a model nobody can obtain is the defect.

    Resolution is by checksum wherever the result recorded one, since that is
    the identity the zoo exists to provide. The four `mobilenetv2-12.onnx`
    results recorded none, so they fall back to the name -- which is exactly
    the weakness that motivated the module.
    """
    import glob

    entries = load_zoo(ZOO)
    slugs = {_slug(e.key) for e in entries} | {_slug(e.name) for e in entries}
    missing = []
    for result_path in sorted(glob.glob("results/published/*.json")):
        doc = json.loads(Path(result_path).read_text(encoding="utf-8"))
        model = doc.get("model") or {}
        if entry_for_checksum(entries, model.get("checksum")) is not None:
            continue
        if _slug(model.get("name") or "") in slugs:
            continue
        missing.append(f"{Path(result_path).name} -> {model.get('name')}")
    assert not missing, f"published results measure models absent from the zoo: {missing}"


def test_the_corpus_resolves_by_checksum_wherever_it_recorded_one():
    """Five of nine published results carry a checksum; all five must resolve.

    A checksum the zoo cannot place is a model the zoo does not actually
    cover, however convincing the name match looks.
    """
    import glob

    entries = load_zoo(ZOO)
    unresolved = []
    for result_path in sorted(glob.glob("results/published/*.json")):
        doc = json.loads(Path(result_path).read_text(encoding="utf-8"))
        checksum = (doc.get("model") or {}).get("checksum")
        if checksum and entry_for_checksum(entries, checksum) is None:
            unresolved.append(f"{Path(result_path).name} -> {checksum}")
    assert not unresolved, f"checksums no zoo entry accounts for: {unresolved}"


def test_declared_licences_carry_their_basis():
    """`declared` means a human wrote it, so the note must say on what basis."""
    for entry in load_zoo(ZOO):
        if entry.license_source == "declared":
            assert entry.notes, f"{entry.key}: a declared licence needs a documented basis"
            assert entry.license_link, f"{entry.key}: a declared licence needs a link to the terms"


def test_the_vocabularies_are_closed():
    assert CHECKSUM_KINDS == {"weights-sha256", "ollama-manifest-sha256"}
    assert LICENSE_SOURCES == {"gguf-header", "ollama-api", "declared"}


def test_obtainable_is_about_the_manifest_not_the_disk():
    entry = ZooEntry(key="k", name="n", format="gguf", source={"kind": "unavailable"})
    assert entry.obtainable is False
    assert ZooEntry(key="k", name="n", format="gguf", source={"kind": "ollama"}).obtainable is True


# --- attention geometry ---------------------------------------------------


def test_a_partial_geometry_is_rejected(tmp_path):
    """Half a geometry yields a confident wrong cache size, not no answer.

    `kv_cache_bytes_per_token` returns None when a field is missing, so a
    manifest carrying two of the three would silently produce nothing where a
    reader expects a number -- or worse, be "fixed" later by defaulting the
    missing one.
    """
    path = _write(tmp_path, _entry(attention={"block_count": 24, "head_count_kv": 2}))
    with pytest.raises(ZooError, match="head_dim"):
        load_zoo(path)


def test_geometry_is_optional_because_not_every_format_states_it(tmp_path):
    """ONNX carries no attention metadata, and is not thereby broken."""
    path = _write(tmp_path, _entry(attention=None))
    assert load_zoo(path)[0].attention is None


def test_the_recorded_geometry_sizes_the_cache_the_measurements_confirmed():
    """The zoo's geometry must reproduce the published KV-cache study.

    The dashboard computes cache sizes from this manifest rather than from the
    weights, because the weights are the one thing that cannot be shipped.
    A wrong geometry here would put wrong numbers on the site with nothing to
    catch them.
    """
    from aihwbench.analysis.kvcache import BYTES_PER_MB, kv_cache_bytes

    entry = next(e for e in load_zoo(ZOO) if e.key == "qwen2.5-0.5b-instruct-q4_k_m")
    assert entry.attention is not None
    at_f16 = kv_cache_bytes(entry.attention, 32768, "f16", "f16")
    at_q4 = kv_cache_bytes(entry.attention, 32768, "q4_0", "q4_0")
    assert round(at_f16 / BYTES_PER_MB, 1) == 384.0
    assert round(at_q4 / BYTES_PER_MB, 1) == 108.0
