"""Typed workload engine.

A *workload* is a declarative, versioned description of what is measured:
input/output lengths, sampling parameters, traffic shape, dataset identity,
and capability requirements. Workloads are registered by id so results can
reference exactly what produced them (``workload.id`` + ``workload.version``
in schema 2.0 result documents).

Third-party plugins publish workloads through the ``aihwbench.workloads``
entry-point group::

    [project.entry-points."aihwbench.workloads"]
    my_workload = "my_package.workloads:MY_WORKLOAD"

Entry points may expose a :class:`Workload` instance or a zero-argument
callable returning one.
"""

from __future__ import annotations

import importlib.metadata
from collections.abc import Iterator
from dataclasses import dataclass, field, replace
from typing import Any

__all__ = [
    "Workload",
    "TurnSpec",
    "SamplingParams",
    "DatasetRef",
    "TrafficMixItem",
    "register",
    "get_workload",
    "list_workloads",
    "discover_plugins",
    "ISL_OSL_PROFILES",
]

ENTRY_POINT_GROUP = "aihwbench.workloads"


@dataclass(frozen=True)
class SamplingParams:
    """Deterministic-by-default generation sampling."""

    temperature: float = 0.0
    top_p: float = 1.0
    seed: int = 42


@dataclass(frozen=True)
class DatasetRef:
    """Identity of an optional evaluation/prompt dataset."""

    name: str
    version: str
    hash: str | None = None
    license: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "hash": self.hash,
            "license": self.license,
        }


@dataclass(frozen=True)
class TurnSpec:
    """One turn of a multi-turn conversation."""

    user_prompt: str
    expected_output_tokens: int = 64


@dataclass(frozen=True)
class TrafficMixItem:
    """One component of a mixed traffic distribution (#13)."""

    weight: float
    isl_tokens: int
    osl_tokens: int


@dataclass(frozen=True)
class Workload:
    """A versioned, declarative benchmark workload."""

    id: str
    kind: str  # generation | prefill | decode | combined | multi_turn | agentic
    version: str = "1.0.0"
    description: str = ""
    # Target lengths in tokens. Actual counts are always measured by the
    # runtime and recorded per iteration; these targets shape the request.
    isl_tokens: int | None = None
    osl_tokens: int | None = None
    prompt: str | None = None
    turns: tuple[TurnSpec, ...] = ()
    sampling: SamplingParams = field(default_factory=SamplingParams)
    dataset: DatasetRef | None = None
    # Capability requirements the backend must satisfy to run this workload,
    # e.g. ("streaming",) or ("tool_calls",).
    requires: tuple[str, ...] = ()
    # Mixed traffic components (mutually exclusive with single isl/osl).
    traffic_mix: tuple[TrafficMixItem, ...] = ()

    def __post_init__(self) -> None:
        if not self.id or any(c.isspace() for c in self.id):
            raise ValueError(f"workload id must be non-empty without whitespace: {self.id!r}")
        allowed_kinds = {"generation", "prefill", "decode", "combined", "multi_turn", "agentic"}
        if self.kind not in allowed_kinds:
            raise ValueError(
                f"workload kind must be one of {sorted(allowed_kinds)}, got {self.kind!r}"
            )
        if self.kind == "multi_turn" and not self.turns:
            raise ValueError(f"multi_turn workload {self.id!r} requires at least one turn")
        if self.traffic_mix:
            total = sum(item.weight for item in self.traffic_mix)
            if abs(total - 1.0) > 1e-9:
                raise ValueError(
                    f"workload {self.id!r} traffic_mix weights must sum to 1.0, got {total}"
                )

    def with_overrides(self, **changes: Any) -> Workload:
        """Return a copy with fields replaced (used by sweeps/manifests)."""
        return replace(self, **changes)

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": self.id,
            "kind": self.kind,
            "version": self.version,
            "description": self.description,
            "isl_tokens": self.isl_tokens,
            "osl_tokens": self.osl_tokens,
            "sampling": {
                "temperature": self.sampling.temperature,
                "top_p": self.sampling.top_p,
                "seed": self.sampling.seed,
            },
            "requires": list(self.requires),
        }
        if self.prompt is not None:
            out["prompt"] = self.prompt
        if self.turns:
            out["turns"] = [
                {
                    "user_prompt": t.user_prompt,
                    "expected_output_tokens": t.expected_output_tokens,
                }
                for t in self.turns
            ]
        if self.dataset is not None:
            out["dataset"] = self.dataset.as_dict()
        if self.traffic_mix:
            out["traffic_mix"] = [
                {"weight": i.weight, "isl_tokens": i.isl_tokens, "osl_tokens": i.osl_tokens}
                for i in self.traffic_mix
            ]
        return out


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, Workload] = {}
_PLUGINS_DISCOVERED = False


def register(workload: Workload) -> Workload:
    """Register a workload under its id (last registration wins)."""
    _REGISTRY[workload.id] = workload
    return workload


def get_workload(workload_id: str) -> Workload:
    """Look up a registered workload by id."""
    _ensure_builtin()
    try:
        return _REGISTRY[workload_id]
    except KeyError:
        known = ", ".join(sorted(_REGISTRY)) or "<none>"
        raise KeyError(f"unknown workload {workload_id!r}; registered: {known}") from None


def list_workloads() -> list[str]:
    """All registered workload ids, sorted."""
    _ensure_builtin()
    return sorted(_REGISTRY)


def discover_plugins() -> Iterator[tuple[str, Workload]]:
    """Yield (id, workload) from installed ``aihwbench.workloads`` plugins.

    Plugin objects may be Workload instances or zero-arg callables that
    return one. Invalid plugin objects are skipped rather than crashing
    discovery for everyone else.
    """
    global _PLUGINS_DISCOVERED
    eps = importlib.metadata.entry_points()
    try:
        group = eps.select(group=ENTRY_POINT_GROUP)
    except AttributeError:  # Python < 3.10 fallback shape
        group = eps.get(ENTRY_POINT_GROUP, [])  # type: ignore[attr-defined]
    for ep in group:
        try:
            obj = ep.load()
            workload = obj() if callable(obj) and not isinstance(obj, Workload) else obj
            if isinstance(workload, Workload):
                yield register(workload).id, workload
        except Exception:
            # A broken third-party plugin must not break the registry.
            continue
    _PLUGINS_DISCOVERED = True


def _ensure_builtin() -> None:
    from . import builtin as _builtin  # noqa: F401  (registers on import)

    if not _PLUGINS_DISCOVERED:
        for _ in discover_plugins():
            pass


# ---------------------------------------------------------------------------
# Standardized ISL/OSL profiles (#12)
# ---------------------------------------------------------------------------

ISL_OSL_PROFILES: dict[str, Workload] = {}


def _profile(workload: Workload) -> Workload:
    ISL_OSL_PROFILES[workload.id] = register(workload)
    return workload


_profile(
    Workload(
        id="chat_short",
        kind="combined",
        description="Short chat exchange: ~128-token prompt, ~128 generated tokens.",
        isl_tokens=128,
        osl_tokens=128,
    )
)
_profile(
    Workload(
        id="long_prompt",
        kind="prefill",
        description="Long-prompt profile: ~4096-token input, short ~128-token output.",
        isl_tokens=4096,
        osl_tokens=128,
    )
)
_profile(
    Workload(
        id="long_generation",
        kind="decode",
        description="Long-generation profile: short ~128-token input, ~1024 generated tokens.",
        isl_tokens=128,
        osl_tokens=1024,
    )
)
_profile(
    Workload(
        id="long_context",
        kind="combined",
        description="Long-context profile: ~8192-token input, ~512 generated tokens.",
        isl_tokens=8192,
        osl_tokens=512,
    )
)
