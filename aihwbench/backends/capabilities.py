"""Runtime capability reporting contract (#7, #8, #10, #11).

Hardware-specific backends (TensorRT, ROCm, QNN, HailoRT) depend on
toolchains and accelerators that most machines lack. This module gives
every such backend a structured, honest capability report:

- which CLI tooling was probed and whether it responded,
- which hardware probes were run and whether the accelerator is present,
- a lifecycle status that never fabricates availability.

The report never executes a benchmark and never estimates performance;
a missing toolchain yields ``NOT_INSTALLED`` and missing hardware yields
``HARDWARE_REQUIRED``.
"""

from __future__ import annotations

from typing import Any

from .base import run_command

__all__ = ["probe", "capability_report"]


def probe(cmd: str, timeout: float = 10.0) -> dict[str, Any]:
    """Run one read-only probe command and report presence honestly.

    ``found`` is true only when the command executed successfully; a
    missing executable or non-zero exit is reported, never hidden.
    """
    argv = cmd.split()
    code, out = run_command(argv, timeout=timeout)
    first = out.splitlines()[0][:160] if out else ""
    return {
        "command": cmd,
        "found": code == 0,
        "exit_code": code,
        "detail": first,
    }


def capability_report(
    runtime: str,
    cli: list[str],
    hardware: list[str],
    guidance: str,
) -> dict[str, Any]:
    """Build the structured capability report for one runtime.

    ``cli`` are toolchain probes; ``hardware`` are accelerator probes
    (empty when the toolchain itself implies hardware presence). Status
    transitions are strict: toolchain + hardware -> ``AVAILABLE``,
    toolchain without hardware -> ``HARDWARE_REQUIRED``, no toolchain ->
    ``NOT_INSTALLED``.
    """
    cli_results = [probe(c) for c in cli]
    hardware_results = [probe(c) for c in hardware]
    cli_found = any(r["found"] for r in cli_results)
    hardware_present: bool | None = (
        all(r["found"] for r in hardware_results) if hardware_results else None
    )
    if cli_found and (hardware_present is None or hardware_present):
        status = "AVAILABLE"
    elif cli_found:
        status = "HARDWARE_REQUIRED"
    else:
        status = "NOT_INSTALLED"
    return {
        "runtime": runtime,
        "cli": cli_results,
        "hardware": hardware_results,
        "hardware_present": hardware_present,
        "status": status,
        "guidance": guidance,
        "note": (
            "capability report only — no benchmark was executed and no "
            "performance values are reported"
        ),
    }
