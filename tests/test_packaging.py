"""Package-manager manifests, generated from a real artifact.

Install friction suppresses submission volume, which is this project's actual
bottleneck: the framework exists and the hardware coverage does not, so every
step between "I have an interesting GPU" and "I ran the benchmark" costs
results.

Manifests are generated, never hand-written. A Homebrew formula or a winget
manifest carries a version and the SHA-256 of one specific file; typing those
by hand produces a manifest that installs nothing, or silently pins an old
release.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import tarfile
from pathlib import Path

import pytest

packaging = importlib.import_module("scripts.generate_packaging")


@pytest.fixture
def fake_dist(tmp_path: Path) -> Path:
    """A directory holding one plausible sdist."""
    dist = tmp_path / "dist"
    dist.mkdir()
    payload = tmp_path / "payload.txt"
    payload.write_text("contents", encoding="utf-8")
    archive = dist / "aihwbench-9.9.9.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(payload, arcname="aihwbench/payload.txt")
    return dist


def test_the_digest_matches_the_real_file(fake_dist: Path):
    """The whole point: the hash describes the artifact, not a guess."""
    sdist = packaging.find_sdist(fake_dist)
    expected = hashlib.sha256(sdist.read_bytes()).hexdigest()
    assert packaging.sha256(sdist) == expected


def test_manifests_are_written_for_every_manager(fake_dist: Path, tmp_path: Path):
    out = tmp_path / "packaging"
    assert (
        packaging.main(["--dist", str(fake_dist), "--output", str(out), "--version", "9.9.9"]) == 0
    )
    assert (out / "aihwbench.rb").is_file()
    assert (out / "aihwbench.json").is_file()
    assert (out / "aihwbench.yaml").is_file()


def test_the_scoop_manifest_is_valid_json_and_carries_the_digest(fake_dist, tmp_path):
    out = tmp_path / "packaging"
    packaging.main(["--dist", str(fake_dist), "--output", str(out), "--version", "9.9.9"])
    manifest = json.loads((out / "aihwbench.json").read_text(encoding="utf-8"))
    digest = packaging.sha256(packaging.find_sdist(fake_dist))
    assert manifest["version"] == "9.9.9"
    assert manifest["hash"] == f"sha256:{digest}"


def test_the_winget_manifest_uses_an_uppercase_digest(fake_dist, tmp_path):
    """winget requires uppercase; a lowercase digest is rejected on submission."""
    out = tmp_path / "packaging"
    packaging.main(["--dist", str(fake_dist), "--output", str(out), "--version", "9.9.9"])
    text = (out / "aihwbench.yaml").read_text(encoding="utf-8")
    digest = packaging.sha256(packaging.find_sdist(fake_dist))
    assert digest.upper() in text


def test_every_manifest_agrees_on_the_version_and_url(fake_dist, tmp_path):
    """Three files describing different releases would be worse than none."""
    out = tmp_path / "packaging"
    packaging.main(["--dist", str(fake_dist), "--output", str(out), "--version", "9.9.9"])
    texts = [
        (out / name).read_text(encoding="utf-8")
        for name in ("aihwbench.rb", "aihwbench.json", "aihwbench.yaml")
    ]
    digest = packaging.sha256(packaging.find_sdist(fake_dist))
    for text in texts:
        assert "9.9.9" in text
        assert "aihwbench-9.9.9.tar.gz" in text
        assert digest in text or digest.upper() in text


def test_a_missing_sdist_is_an_error_not_an_empty_manifest(tmp_path: Path):
    empty = tmp_path / "dist"
    empty.mkdir()
    assert packaging.main(["--dist", str(empty), "--output", str(tmp_path / "out")]) == 1


def test_two_sdists_are_refused_rather_than_guessed(fake_dist: Path, tmp_path: Path):
    """Which release would the manifests describe? Refusing beats choosing."""
    (fake_dist / "aihwbench-8.8.8.tar.gz").write_bytes(b"another")
    with pytest.raises(ValueError, match="Refusing to guess"):
        packaging.find_sdist(fake_dist)


def test_manifests_say_they_are_generated(fake_dist, tmp_path):
    """A hand-edited manifest installs the wrong file; say so in the file."""
    out = tmp_path / "packaging"
    packaging.main(["--dist", str(fake_dist), "--output", str(out), "--version", "9.9.9"])
    for name in ("aihwbench.rb", "aihwbench.yaml"):
        assert "Do not edit by hand" in (out / name).read_text(encoding="utf-8")
