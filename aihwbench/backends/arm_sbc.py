"""ARM single-board computers — Raspberry Pi and friends, CPU-only and honest.

A Pi 5 will not run a 7B model usefully, and that is the finding. This
project's compatibility matrix is worth more for saying where local AI stops
being practical than for another ranking of fast machines, and nobody publishes
the boards that fail.

Three things a benchmark on these boards has to record or the number is
unreproducible, and all three bite harder here than on a laptop:

**Thermal throttling is the normal state, not an anomaly.** A Pi under
sustained load throttles within minutes without a heatsink, so a short run
measures the unthrottled board and a long one measures a different machine. The
throttle flags are readable and belong in the result.

**Power delivery is frequently the limit.** An undervolted Pi silently reduces
clocks, and the resulting number looks like a slow board rather than a bad
power supply. `vcgencmd get_throttled` reports both, and the two are
distinguishable only if you ask.

**Memory is the hard wall.** These boards have 2–16 GB shared between system
and model, no swap worth using, and the failure mode is the OOM killer rather
than a slowdown. What fits is the interesting measurement.

Detection identifies the board from the device tree rather than guessing from
the architecture: plenty of aarch64 machines are not SBCs, and an Apple Silicon
Mac is aarch64 too.
"""

from __future__ import annotations

import platform
import re
from pathlib import Path
from typing import Any

from .base import BackendError, BackendInfo, BenchmarkConfig, RuntimeStatus, run_command

_DEVICE_TREE_MODEL = Path("/proc/device-tree/model")

#: Boards whose device-tree model this recognises. Matching on the board's own
#: declared name rather than on the architecture, because aarch64 includes
#: Apple Silicon, Ampere servers and Jetsons, none of which is an SBC.
_KNOWN_BOARDS = (
    "raspberry pi",
    "orange pi",
    "rock pi",
    "radxa",
    "odroid",
    "banana pi",
    "khadas",
    "libre computer",
)

#: `vcgencmd get_throttled` returns a bit field, e.g. `throttled=0x50005`.
_THROTTLED = re.compile(r"throttled\s*=\s*0x([0-9a-fA-F]+)")

#: What each bit means. The distinction that matters is under-voltage (a power
#: supply problem, fixable) against thermal (a cooling problem, also fixable) --
#: both of which look like "this board is slow" if nobody reads the flags.
_THROTTLE_BITS = {
    0: "under-voltage now",
    1: "arm frequency capped now",
    2: "currently throttled",
    3: "soft temperature limit now",
    16: "under-voltage has occurred",
    17: "arm frequency capping has occurred",
    18: "throttling has occurred",
    19: "soft temperature limit has occurred",
}


def board_model() -> str | None:
    """The board's declared name, if it is one this recognises."""
    try:
        if _DEVICE_TREE_MODEL.is_file():
            raw = _DEVICE_TREE_MODEL.read_text(encoding="utf-8", errors="replace")
            model = raw.replace(chr(0), "").strip()
            if any(board in model.lower() for board in _KNOWN_BOARDS):
                return model
    except OSError:  # pragma: no cover - platform dependent
        pass
    return None


def throttle_state() -> dict[str, Any]:
    """Whether the board is being held back, and by what.

    Returns `flags: None` when it cannot be read: unknown, which is not the
    same as "not throttled" and must not be recorded as it.
    """
    code, out = run_command(["vcgencmd", "get_throttled"], timeout=20.0)
    if code != 0 or not out:
        return {
            "flags": None,
            "raw": None,
            "reason": "vcgencmd is unavailable, so throttling state is unknown",
        }
    match = _THROTTLED.search(out)
    if not match:
        return {"flags": None, "raw": out.strip(), "reason": "unrecognised vcgencmd output"}

    value = int(match.group(1), 16)
    return {
        "flags": [label for bit, label in _THROTTLE_BITS.items() if value & (1 << bit)],
        "raw": f"0x{value:x}",
        "throttled_now": bool(value & 0b1111),
        "throttled_ever": bool(value >> 16),
        "reason": None,
    }


def detect() -> BackendInfo:
    model = board_model()
    if not model:
        machine = platform.machine()
        return BackendInfo(
            "arm_sbc",
            RuntimeStatus.HARDWARE_REQUIRED,
            None,
            f"No recognised single-board computer found (machine is {machine}). "
            "This backend targets Raspberry Pi, Orange Pi, Radxa, ODROID and "
            "similar boards, identified by their device-tree model.",
        )

    state = throttle_state()
    detail = model
    if state["flags"]:
        detail = f"{model}; throttling: {', '.join(state['flags'])}"
    elif state["reason"]:
        detail = f"{model}; {state['reason']}"
    return BackendInfo("arm_sbc", RuntimeStatus.AVAILABLE, None, detail)


def run(config: BenchmarkConfig, system: dict[str, Any]) -> dict[str, Any]:
    """Benchmark on an SBC through llama.cpp, recording the throttle state.

    The throttle flags are captured after the run as well as before, because
    the interesting case is a board that started cool and did not stay that
    way -- which is the normal outcome on a passively cooled Pi and would
    otherwise be reported as a slow board.
    """
    info = detect()
    if info.status is not RuntimeStatus.AVAILABLE:
        raise BackendError(f"arm_sbc is not available: {info.status.value} ({info.detail})")

    from . import llama_cpp

    before = throttle_state()
    result = llama_cpp.run(config, system)
    after = throttle_state()

    result["runtime"]["name"] = "arm_sbc"
    result["runtime"]["backend"] = "llama.cpp-cpu"
    result.setdefault("system", {})["board"] = board_model()
    result.setdefault("system", {})["memory_is_unified"] = True
    result.setdefault("reproducibility", {})["throttling"] = {
        "before": before,
        "after": after,
        # The measurement that explains a disappointing number.
        "throttled_during_run": bool(after.get("throttled_ever"))
        and not bool(before.get("throttled_ever")),
    }
    return result


#: Declared capability contract: truthful prerequisites and quirks.
CAPABILITIES: tuple[str, ...] = (
    "arm-sbc-required",
    "cpu-only",
    "unified-memory",
    "thermal-throttling-expected",
    "power-delivery-can-limit-clocks",
)
