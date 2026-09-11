"""What devices a runtime can actually offload to, and how to split across them.

Two questions this answers that `detect_system` does not.

**Which devices does the *runtime* see?** Not which the machine has. This
laptop has an Intel Iris Xe and an RTX 3080 Ti, and Vulkan enumerates both --
but a CUDA build of llama.cpp offloads to exactly one of them. A multi-GPU
sweep planned from the hardware inventory would ask for a split the runtime
cannot perform, and llama.cpp's response to an over-long `--tensor-split` is to
ignore the extra entries rather than complain.

**How is a split expressed?** `--tensor-split` takes one fraction per device,
in device order. Get the count wrong and the run proceeds with a different
split from the one requested, producing a real measurement of a configuration
nobody asked for.

A `ggml-rpc-server` counts as a device, which is what makes a two-device split
testable on a one-GPU machine: the RPC backend appears alongside CUDA0 in the
same enumeration and takes its share of the tensor split.
"""

from __future__ import annotations

import re
import subprocess
from typing import Any

__all__ = [
    "device_inventory",
    "parse_device_list",
    "validate_tensor_split",
    "SPLIT_MODES",
]

#: `  CUDA0: NVIDIA GeForce RTX 3080 Ti Laptop GPU (16383 MiB, 15239 MiB free)`
_DEVICE_LINE = re.compile(
    r"^\s*([A-Za-z0-9_.:]+):\s*(.+?)\s*\((\d+)\s*MiB(?:,\s*(\d+)\s*MiB free)?\)\s*$"
)

#: How llama.cpp may divide a model across devices.
SPLIT_MODES = ("none", "layer", "row")


def parse_device_list(text: str) -> list[dict[str, Any]]:
    """Devices from `llama-server --list-devices` output.

    Order is preserved, because `--tensor-split` is positional: the first
    fraction goes to the first device listed, and a set of fractions read
    against a different order silently measures a different configuration.
    """
    devices: list[dict[str, Any]] = []
    for line in (text or "").splitlines():
        if line.strip().lower().startswith("available devices"):
            continue
        match = _DEVICE_LINE.match(line)
        if not match:
            continue
        identifier, description, total, free = match.groups()
        devices.append(
            {
                "id": identifier,
                "description": description,
                "total_mib": int(total),
                "free_mib": int(free) if free else None,
                # RPC devices are remote and their memory is somebody else's
                # machine; worth distinguishing from a local card when
                # reporting what a split ran on.
                "kind": "rpc" if identifier.upper().startswith("RPC") else "local",
            }
        )
    return devices


def device_inventory(
    binary: str | None = None,
    rpc_servers: str | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    """Ask llama.cpp which devices it can offload to.

    `rpc_servers` is passed through because an RPC backend only appears in the
    enumeration when the runtime was told where to find it -- so "what devices
    are available" genuinely depends on the answer you were going to give.
    """
    from .backends.llama_cpp import _find_binary

    executable = binary or _find_binary("llama-server")
    if not executable:
        return {
            "devices": [],
            "unresolved": "llama-server was not found, so no device list could be read",
        }

    # `--rpc` must precede `--list-devices`: llama.cpp acts on the list
    # request as it parses it and exits, so a later `--rpc` is never read and
    # the remote device is missing from a list that looks complete.
    command = [executable]
    if rpc_servers:
        command += ["--rpc", rpc_servers]
    command.append("--list-devices")
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"devices": [], "unresolved": f"could not list devices: {exc}"}

    devices = parse_device_list((proc.stdout or "") + (proc.stderr or ""))
    return {
        "devices": devices,
        "device_count": len(devices),
        "rpc_servers": rpc_servers,
        "unresolved": None if devices else "the runtime reported no offload devices",
    }


def validate_tensor_split(split: str, device_count: int) -> dict[str, Any]:
    """Check a `--tensor-split` against the devices that actually exist.

    llama.cpp does not refuse a split with the wrong number of entries: extra
    fractions are ignored and missing ones default. Either way the run
    proceeds and measures a configuration that is not the one requested, which
    is a worse outcome than an error because the number looks fine.
    """
    try:
        fractions = [float(part) for part in split.split(",") if part.strip()]
    except ValueError:
        return {"valid": False, "reason": f"{split!r} is not a comma-separated list of numbers"}

    if not fractions:
        return {"valid": False, "reason": "an empty tensor split selects nothing"}
    if any(f < 0 for f in fractions):
        return {"valid": False, "reason": "a negative share is not a share"}
    if sum(fractions) <= 0:
        return {
            "valid": False,
            "reason": "the shares sum to zero, so no device would hold anything",
        }
    if len(fractions) != device_count:
        return {
            "valid": False,
            "reason": (
                f"{len(fractions)} share(s) for {device_count} device(s). llama.cpp "
                "ignores the extras and defaults the missing ones rather than "
                "failing, so the run would measure a split nobody requested."
            ),
        }

    total = sum(fractions)
    return {
        "valid": True,
        "reason": None,
        "fractions": fractions,
        # llama.cpp normalizes internally; reporting the normalized shares is
        # what lets a result say how the model was actually divided rather
        # than what was typed.
        "normalized": [round(f / total, 4) for f in fractions],
    }
