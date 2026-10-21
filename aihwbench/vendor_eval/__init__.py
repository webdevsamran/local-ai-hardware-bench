"""Vendor evaluation framework for local AI hardware accelerators.

Provides standardized data models, on-device run planning, concurrency &
ISL/OSL matrix definitions, service level objective (SLO) compliance checkers,
and vendor telemetry abstractions.

Designed for on-device and remote workstation hardware evaluations (FuriosaAI RNGD,
Tenstorrent Wormhole/Blackhole, Intel Gaudi, Untether, SambaNova, Groq, etc.).
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Mapping, Sequence


# Standard conversational SLO threshold (tokens/second per active stream)
DEFAULT_CONVERSATIONAL_SLO_TPS: float = 40.0


@dataclass(frozen=True)
class ISLOSLPair:
    """Canonical input/output sequence length pair for matrix evaluation."""

    input_tokens: int
    output_tokens: int
    label: str = ""

    def __post_init__(self) -> None:
        if not self.label:
            object.__setattr__(self, "label", f"{self.input_tokens}/{self.output_tokens}")


# Canonical ISL/OSL evaluation grid recommended for hardware vendor reviews
STANDARD_ISL_OSL_GRID: tuple[ISLOSLPair, ...] = (
    ISLOSLPair(128, 128),
    ISLOSLPair(128, 1024),
    ISLOSLPair(1024, 128),
    ISLOSLPair(1024, 1024),
    ISLOSLPair(2048, 1024),
    ISLOSLPair(4096, 1024),
    ISLOSLPair(8192, 1024),
    ISLOSLPair(16384, 1024),
    ISLOSLPair(31744, 1024),
)

STANDARD_CONCURRENCY_SWEEP: tuple[int, ...] = (1, 2, 4, 8, 16, 32, 64, 128, 256, 512)
STANDARD_POOLING_BATCH_SWEEP: tuple[int, ...] = (1, 2, 4, 8, 16, 32, 64)
STANDARD_POOLING_SEQ_SWEEP: tuple[int, ...] = (128, 256, 512, 1024, 2048)


@dataclass
class VendorModelSpec:
    """Specification of a model to evaluate on vendor hardware."""

    model_id: str
    task: str = "generate"  # generate | vlm | embed | score
    display_name: str = ""
    notes: list[str] = field(default_factory=list)
    args: list[str] = field(default_factory=list)
    isl_osl_grid: list[tuple[int, int]] = field(default_factory=list)
    concurrency_sweep: list[int] = field(default_factory=list)
    is_in_scope: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "task": self.task,
            "display_name": self.display_name or self.model_id,
            "notes": list(self.notes),
            "args": list(self.args),
            "isl_osl_grid": self.isl_osl_grid,
            "concurrency_sweep": self.concurrency_sweep,
            "is_in_scope": self.is_in_scope,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> VendorModelSpec:
        return cls(
            model_id=str(data["model_id"]),
            task=str(data.get("task", "generate")),
            display_name=str(data.get("display_name", "")),
            notes=list(data.get("notes", [])),
            args=list(data.get("args", [])),
            isl_osl_grid=[tuple(x) for x in data.get("isl_osl_grid", [])],  # type: ignore
            concurrency_sweep=list(data.get("concurrency_sweep", [])),
            is_in_scope=bool(data.get("is_in_scope", True)),
        )


@dataclass
class VendorEvalPlan:
    """Master benchmark plan for a vendor hardware evaluation."""

    vendor_name: str
    hardware_name: str
    models: list[VendorModelSpec] = field(default_factory=list)
    common_args: list[str] = field(default_factory=list)
    runner_script: str = "furiosa_llm_runner.py"
    min_free_disk_gb: float = 24.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "vendor_name": self.vendor_name,
            "hardware_name": self.hardware_name,
            "models": [m.to_dict() for m in self.models],
            "common_args": list(self.common_args),
            "runner_script": self.runner_script,
            "min_free_disk_gb": self.min_free_disk_gb,
        }

    def save_json(self, path: Path | str) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        return p

    @classmethod
    def load_json(cls, path: Path | str) -> VendorEvalPlan:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(
            vendor_name=str(data.get("vendor_name", "generic")),
            hardware_name=str(data.get("hardware_name", "accelerator")),
            models=[VendorModelSpec.from_dict(m) for m in data.get("models", [])],
            common_args=list(data.get("common_args", [])),
            runner_script=str(data.get("runner_script", "runner.py")),
            min_free_disk_gb=float(data.get("min_free_disk_gb", 24.0)),
        )


def calculate_gross_efficiency(
    tokens_per_second: float | None,
    accelerator_power_watts: float | None,
) -> float | None:
    """Calculate gross energy efficiency in tokens/sec per Watt without idle subtraction.

    Hardware review standards define efficiency as total output tokens per second
    divided by total accelerator draw during the active benchmark window.
    """
    if tokens_per_second is None or accelerator_power_watts is None:
        return None
    if accelerator_power_watts <= 0 or tokens_per_second <= 0:
        return None
    return round(float(tokens_per_second) / float(accelerator_power_watts), 2)


def check_per_user_slo(
    per_user_decode_tps: float | None,
    threshold_tps: float = DEFAULT_CONVERSATIONAL_SLO_TPS,
) -> bool | None:
    """Check if per-stream generation throughput satisfies the conversational reading SLO.

    Human reading speed tops out at ~20-30 tok/s; a 40 tok/s per-user stream
    guarantees responsive user experience even with streaming token delivery.
    """
    if per_user_decode_tps is None:
        return None
    return per_user_decode_tps >= threshold_tps


__all__ = [
    "DEFAULT_CONVERSATIONAL_SLO_TPS",
    "ISLOSLPair",
    "STANDARD_ISL_OSL_GRID",
    "STANDARD_CONCURRENCY_SWEEP",
    "STANDARD_POOLING_BATCH_SWEEP",
    "STANDARD_POOLING_SEQ_SWEEP",
    "VendorModelSpec",
    "VendorEvalPlan",
    "calculate_gross_efficiency",
    "check_per_user_slo",
]
