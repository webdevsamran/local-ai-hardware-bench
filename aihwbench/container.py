"""Container identity, for results produced inside one.

A benchmark run in a container is only reproducible if the *image* is
identifiable, and a tag is not an identity. `ollama/ollama:latest` names
something different every week; two results measured a month apart against
"the same image" can differ in the runtime, the CUDA libraries and the kernel
they were built against, while both claiming the same tag.

The digest is the identity. This module records it where it can be found, and
records the absence honestly where it cannot -- which is most of the time,
because Docker does not expose the digest of the running image to the
container by default. Saying "in a container, digest unknown" is a different
and more useful statement than saying nothing, since it tells a reader that
the environment block does not describe the whole environment.

Nothing here is inferred beyond what the runtime actually exposes. A guessed
digest would be worse than none: it would make two different images look like
one, which is exactly the comparison this project exists to prevent.
"""

from __future__ import annotations

import os
import platform
from pathlib import Path
from typing import Any

__all__ = ["container_info", "IMAGE_DIGEST_ENV"]

#: Environment variables an image build can set so the digest travels with the
#: run. Docker exposes no digest to the container itself, so this has to be
#: written in at build or launch time -- `docker run -e
#: AIHWBENCH_IMAGE_DIGEST=$(docker inspect --format='{{index .RepoDigests 0}}'
#: <image>)`. Several names are accepted because CI systems already set their
#: own, and reusing one the platform provides is more reliable than asking
#: every contributor to remember a new one.
IMAGE_DIGEST_ENV: tuple[str, ...] = (
    "AIHWBENCH_IMAGE_DIGEST",
    "IMAGE_DIGEST",
    # GitHub Actions container jobs.
    "GITHUB_ACTION_REPOSITORY_DIGEST",
)

_IMAGE_REF_ENV: tuple[str, ...] = ("AIHWBENCH_IMAGE", "IMAGE_REF", "IMAGE_NAME")


def _first_env(names: tuple[str, ...]) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value.strip()
    return None


def _in_container() -> tuple[bool, str | None]:
    """Whether this process is running in a container, and how we know.

    Detection is best-effort by design. A false negative costs a field; a
    false positive would attach container semantics to a bare-metal run, so
    each signal below has to be specific rather than suggestive.
    """
    if os.environ.get("AIHWBENCH_IN_CONTAINER") == "1":
        return True, "AIHWBENCH_IN_CONTAINER"

    if platform.system() != "Linux":
        # Docker Desktop on Windows and macOS runs the container in a Linux
        # VM, so a Windows process is never itself inside one.
        return False, None

    # Docker writes this file into every container it creates.
    if Path("/.dockerenv").exists():
        return True, "/.dockerenv"

    # Podman and some Kubernetes runtimes.
    if Path("/run/.containerenv").exists():
        return True, "/run/.containerenv"

    try:
        cgroup = Path("/proc/self/cgroup").read_text(encoding="utf-8")
    except OSError:
        return False, None
    for marker in ("/docker/", "/docker-", "containerd", "/kubepods"):
        if marker in cgroup:
            return True, "/proc/self/cgroup"
    return False, None


def container_info() -> dict[str, Any]:
    """Container and image identity for the environment block.

    Always returns the same shape, so a consumer never has to distinguish
    "field absent" from "not in a container". ``image_digest`` is null unless
    the digest was supplied to the container, and ``digest_note`` says why.
    """
    in_container, evidence = _in_container()
    digest = _first_env(IMAGE_DIGEST_ENV) if in_container else None
    image = _first_env(_IMAGE_REF_ENV) if in_container else None

    if not in_container:
        note = "not running in a container"
    elif digest:
        note = "digest supplied by the image or launch environment"
    else:
        note = (
            "running in a container, but no image digest was supplied. Docker "
            "does not expose it to the container; pass it in with "
            "-e AIHWBENCH_IMAGE_DIGEST=$(docker inspect "
            "--format='{{index .RepoDigests 0}}' <image>). Without it this "
            "result records the software it measured but not the image that "
            "provided it, and a tag is not an identity"
        )

    return {
        "in_container": in_container,
        "detected_by": evidence,
        "image": image,
        # Never inferred. A guessed digest would make two different images
        # look like one, which is the comparison this project exists to stop.
        "image_digest": digest,
        "digest_note": note,
    }
