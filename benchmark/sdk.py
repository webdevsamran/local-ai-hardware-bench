"""Public Python SDK (#46).

Typed, stdlib-first dataclasses covering the core domain objects:

- ``SystemInfo``, ``RuntimeInfo``, ``ModelInfo`` — environment identity
- ``MetricSet`` — one measured metric collection
- ``Workload`` — workload definition reference
- ``BenchmarkResult`` — a full result document wrapper
- ``BenchmarkRunner`` — thin runner facade over the backend registry
- ``RegressionReport`` — regression check output

All constructors accept plain dicts (e.g. loaded result JSON) so existing
published results convert losslessly; unknown fields are preserved on
``extra``. Unavailable metrics stay ``None``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "SystemInfo",
    "RuntimeInfo",
    "ModelInfo",
    "MetricSet",
    "Workload",
    "BenchmarkResult",
    "BenchmarkRunner",
    "RegressionReport",
]


def _pick(source: Mapping[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    return {k: source.get(k) for k in keys if k in source}


@dataclass(frozen=True)
class SystemInfo:
    os: str | None = None
    os_version: str | None = None
    cpu: str | None = None
    cpu_cores_physical: int | None = None
    cpu_cores_logical: int | None = None
    gpu: str | None = None
    gpu_vram_mb: float | None = None
    npu: str | None = None
    ram_gb: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SystemInfo:
        known = _pick(
            data,
            (
                "os",
                "os_version",
                "cpu",
                "cpu_cores_physical",
                "cpu_cores_logical",
                "gpu",
                "gpu_vram_mb",
                "npu",
                "ram_gb",
            ),
        )
        extra = {k: v for k, v in data.items() if k not in known}
        return cls(**known, extra=extra)

    def to_dict(self) -> dict[str, Any]:
        out = {k: v for k, v in self.__dict__.items() if k != "extra"}
        out.update(self.extra)
        return {k: v for k, v in out.items() if v is not None}


@dataclass(frozen=True)
class RuntimeInfo:
    name: str
    version: str | None = None
    backend: str | None = None
    device: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> RuntimeInfo:
        known = _pick(data, ("name", "version", "backend", "device"))
        extra = {k: v for k, v in data.items() if k not in known}
        return cls(**known, extra=extra)


@dataclass(frozen=True)
class ModelInfo:
    name: str
    format: str | None = None
    quantization: str | None = None
    revision: str | None = None
    checksum: str | None = None
    tokenizer: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ModelInfo:
        known = _pick(data, ("name", "format", "quantization", "revision", "checksum", "tokenizer"))
        extra = {k: v for k, v in data.items() if k not in known}
        return cls(**known, extra=extra)


@dataclass(frozen=True)
class MetricSet:
    """One measured metrics block. Missing measurements are None."""

    generation_tokens_per_second: float | None = None
    prompt_tokens_per_second: float | None = None
    ttft_ms: float | None = None
    latency_p50_ms: float | None = None
    latency_p95_ms: float | None = None
    latency_p99_ms: float | None = None
    peak_vram_mb: float | None = None
    peak_ram_mb: float | None = None
    average_power_watts: float | None = None
    energy_joules_per_token: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> MetricSet:
        known = _pick(
            data,
            (
                "generation_tokens_per_second",
                "prompt_tokens_per_second",
                "ttft_ms",
                "latency_p50_ms",
                "latency_p95_ms",
                "latency_p99_ms",
                "peak_vram_mb",
                "peak_ram_mb",
                "average_power_watts",
                "energy_joules_per_token",
            ),
        )
        extra = {k: v for k, v in data.items() if k not in known}
        return cls(**known, extra=extra)


@dataclass(frozen=True)
class Workload:
    id: str
    version: str = "1.0"
    input_length_profile: str | None = None
    output_length_profile: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Workload:
        known = _pick(data, ("id", "version", "input_length_profile", "output_length_profile"))
        extra = {k: v for k, v in data.items() if k not in known}
        return cls(**known, extra=extra)


@dataclass(frozen=True)
class BenchmarkResult:
    run_id: str
    schema_version: str
    timestamp_utc: str | None = None
    system: SystemInfo | None = None
    runtime: RuntimeInfo | None = None
    model: ModelInfo | None = None
    workload: Workload | None = None
    metrics: MetricSet | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> BenchmarkResult:
        return cls(
            run_id=data.get("run_id") or "",
            schema_version=data.get("schema_version") or "1.0",
            timestamp_utc=data.get("timestamp_utc"),
            system=SystemInfo.from_dict(data["system"]) if data.get("system") else None,
            runtime=RuntimeInfo.from_dict(data["runtime"]) if data.get("runtime") else None,
            model=ModelInfo.from_dict(data["model"]) if data.get("model") else None,
            workload=Workload.from_dict(data["workload"]) if data.get("workload") else None,
            metrics=MetricSet.from_dict(data["metrics"]) if data.get("metrics") else None,
            raw=dict(data),
        )

    @property
    def throughput(self) -> float | None:
        return self.metrics.generation_tokens_per_second if self.metrics else None


@dataclass(frozen=True)
class RegressionCheck:
    metric: str
    status: str
    baseline: float | None
    candidate: float | None
    delta_pct: float | None
    reason: str | None = None


@dataclass(frozen=True)
class RegressionReport:
    classification: str
    status: str
    checks: list[RegressionCheck]

    @classmethod
    def from_report(cls, report: Any) -> RegressionReport:
        checks = [
            RegressionCheck(
                metric=c.metric,
                status=c.status,
                baseline=c.baseline,
                candidate=c.candidate,
                delta_pct=c.delta_pct,
                reason=c.reason,
            )
            for c in getattr(report, "checks", [])
        ]
        return cls(report.classification, report.status, checks)


class BenchmarkRunner:
    """Facade over the runtime backend registry."""

    def __init__(self) -> None:
        from .backends import BACKENDS, resolve

        self._BACKENDS = BACKENDS
        self._resolve = resolve

    @property
    def available_runtimes(self) -> list[str]:
        return sorted(self._BACKENDS)

    def run(self, runtime: str, config: Any) -> dict[str, Any]:
        from .runner import run_benchmark

        self._resolve(runtime)
        return run_benchmark(runtime, config)
