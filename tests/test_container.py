"""Container and image identity in published results.

A benchmark run inside a container is only reproducible if the image is
identifiable, and a tag is not an identity: `ollama/ollama:latest` names
something different every week, so two results a month apart can claim the
same image while having measured different runtimes, CUDA libraries and
kernels.

These tests run on a machine that is not in a container, so every container
path is exercised through the filesystem and environment signals rather than
by being in one.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from aihwbench.container import IMAGE_DIGEST_ENV, container_info


def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (*IMAGE_DIGEST_ENV, "AIHWBENCH_IMAGE", "IMAGE_REF", "IMAGE_NAME"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("AIHWBENCH_IN_CONTAINER", raising=False)


def test_reports_not_in_a_container_on_this_machine(monkeypatch):
    _clear_env(monkeypatch)
    info = container_info()
    assert info["in_container"] is False
    assert info["image_digest"] is None
    assert info["digest_note"] == "not running in a container"


def test_shape_is_the_same_either_way(monkeypatch):
    """A consumer must never have to tell "field absent" from "not in one"."""
    _clear_env(monkeypatch)
    outside = container_info()
    monkeypatch.setenv("AIHWBENCH_IN_CONTAINER", "1")
    inside = container_info()
    assert set(outside) == set(inside)


def test_records_a_digest_that_was_supplied(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("AIHWBENCH_IN_CONTAINER", "1")
    monkeypatch.setenv("AIHWBENCH_IMAGE_DIGEST", "ollama/ollama@sha256:abc123")
    monkeypatch.setenv("AIHWBENCH_IMAGE", "ollama/ollama:0.32.15")

    info = container_info()
    assert info["in_container"] is True
    assert info["image_digest"] == "ollama/ollama@sha256:abc123"
    assert info["image"] == "ollama/ollama:0.32.15"
    assert "supplied" in info["digest_note"]


def test_says_why_the_digest_is_missing_rather_than_going_quiet(monkeypatch):
    """ "In a container, digest unknown" is the useful statement.

    It tells a reader the environment block does not describe the whole
    environment. Silence lets them assume it does.
    """
    _clear_env(monkeypatch)
    monkeypatch.setenv("AIHWBENCH_IN_CONTAINER", "1")

    info = container_info()
    assert info["in_container"] is True
    assert info["image_digest"] is None
    assert "does not expose it" in info["digest_note"]
    # And says how to fix it, since the fix is one flag at launch.
    assert "AIHWBENCH_IMAGE_DIGEST" in info["digest_note"]


def test_never_infers_a_digest_from_an_image_tag(monkeypatch):
    """A guessed digest would make two different images look like one.

    That is precisely the false equivalence the comparison classifier exists
    to prevent, so a tag must never be promoted into the digest field.
    """
    _clear_env(monkeypatch)
    monkeypatch.setenv("AIHWBENCH_IN_CONTAINER", "1")
    monkeypatch.setenv("AIHWBENCH_IMAGE", "ollama/ollama:latest")

    info = container_info()
    assert info["image"] == "ollama/ollama:latest"
    assert info["image_digest"] is None


def test_detects_docker_by_its_marker_file(monkeypatch, tmp_path):
    """Docker writes /.dockerenv into every container it creates."""
    import aihwbench.container as container

    monkeypatch.setattr(container.platform, "system", lambda: "Linux")
    # `as_posix`, not `str`: these tests run on Windows, where
    # `Path("/.dockerenv")` renders with a backslash.
    monkeypatch.setattr(container.Path, "exists", lambda self: self.as_posix() == "/.dockerenv")
    _clear_env(monkeypatch)

    info = container_info()
    assert info["in_container"] is True
    assert info["detected_by"] == "/.dockerenv"


def test_detects_a_container_from_cgroup(monkeypatch):
    import aihwbench.container as container

    monkeypatch.setattr(container.platform, "system", lambda: "Linux")
    monkeypatch.setattr(container.Path, "exists", lambda self: False)
    monkeypatch.setattr(
        container.Path,
        "read_text",
        lambda self, encoding="utf-8": "12:cpu:/docker/9f2c1b4e\n",
    )
    _clear_env(monkeypatch)

    info = container_info()
    assert info["in_container"] is True
    assert info["detected_by"] == "/proc/self/cgroup"


def test_an_ordinary_linux_cgroup_is_not_a_container(monkeypatch):
    """A false positive attaches container semantics to a bare-metal run."""
    import aihwbench.container as container

    monkeypatch.setattr(container.platform, "system", lambda: "Linux")
    monkeypatch.setattr(container.Path, "exists", lambda self: False)
    monkeypatch.setattr(
        container.Path,
        "read_text",
        lambda self, encoding="utf-8": "0::/user.slice/user-1000.slice\n",
    )
    _clear_env(monkeypatch)

    assert container_info()["in_container"] is False


def test_windows_is_never_itself_in_a_container(monkeypatch):
    """Docker Desktop runs the container in a Linux VM, not in this process."""
    import aihwbench.container as container

    monkeypatch.setattr(container.platform, "system", lambda: "Windows")
    _clear_env(monkeypatch)

    assert container_info()["in_container"] is False


def test_an_unreadable_cgroup_is_not_a_container(monkeypatch):
    import aihwbench.container as container

    monkeypatch.setattr(container.platform, "system", lambda: "Linux")
    monkeypatch.setattr(container.Path, "exists", lambda self: False)

    def boom(self, encoding="utf-8"):
        raise OSError("permission denied")

    monkeypatch.setattr(container.Path, "read_text", boom)
    _clear_env(monkeypatch)

    assert container_info()["in_container"] is False


def test_published_results_carry_the_block():
    """Every schema-2.0 result records what environment produced it."""
    import json

    root = Path(__file__).resolve().parent.parent
    for path in sorted((root / "results" / "published").glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        if doc.get("schema_version") != "2.0":
            continue  # 1.0 predates the field
        container = (doc.get("reproducibility") or {}).get("container")
        assert container is not None, f"{path.name} has no container block"
        assert "in_container" in container
        assert "digest_note" in container
