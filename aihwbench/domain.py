"""Typed domain model for AIHWBench.

Stdlib-first dataclasses mirroring the result schema. These types are the
public SDK surface (see ``benchmark.sdk``): they parse schema 1.0 and 2.0
result documents, never invent values, and keep unavailable metrics as
``None``.

All ``from_dict`` constructors are lenient about missing optional fields
(they become ``None``) and strict about types of fields that are present.
Pass ``strict=True`` to raise :class:`DomainParseError` on a wrong-typed
field instead of silently turning it into ``None`` — corrupt input is never
disguised as "not measured".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "DomainParseError",
    "SystemInfo",
    "GpuInfo",
    "TopologyInfo",
    "RuntimeInfo",
    "ModelInfo",
    "WorkloadInfo",
    "MetricSet",
    "IterationSample",
    "TelemetrySummary",
    "ReproducibilityInfo",
    "ProvenanceInfo",
    "BenchmarkResult",
]


class DomainParseError(ValueError):
    """Raised when a strict parse encounters a wrong-typed field.

    In strict mode a wrong-typed value is an error, not "not measured".
    In lenient mode the same value becomes ``None`` (backwards compatible).
    """


def _num(value: Any, strict: bool = False) -> float | None:
    """Coerce a JSON number to float.

    ``None`` passes through as None ("not present"). Wrong types return None
    in lenient mode and raise :class:`DomainParseError` in strict mode.
    Bools are rejected in both modes (JSON true/false is not a number).
    """
    if value is None:
        return None
    if isinstance(value, bool):
        if strict:
            raise DomainParseError(f"expected a number, got boolean {value!r}")
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if strict:
        raise DomainParseError(f"expected a number, got {type(value).__name__} {value!r}")
    return None


def _int(value: Any, strict: bool = False) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        if strict:
            raise DomainParseError(f"expected an integer, got boolean {value!r}")
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if strict:
        raise DomainParseError(f"expected an integer, got {type(value).__name__} {value!r}")
    return None


def _str(value: Any, strict: bool = False) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if strict:
        raise DomainParseError(f"expected a string, got {type(value).__name__} {value!r}")
    return None


@dataclass
class GpuInfo:
    """One discrete/integrated accelerator."""

    vendor: str | None = None
    name: str | None = None
    vram_mb: int | None = None
    driver_version: str | None = None
    compute_capability: str | None = None
    pcie_gen: int | None = None
    pcie_width: int | None = None
    index: int | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any], strict: bool = False) -> GpuInfo:
        return cls(
            vendor=_str(data.get("vendor"), strict),
            name=_str(data.get("name"), strict),
            vram_mb=_int(data.get("vram_mb"), strict),
            driver_version=_str(data.get("driver_version"), strict),
            compute_capability=_str(data.get("compute_capability"), strict),
            pcie_gen=_int(data.get("pcie_gen"), strict),
            pcie_width=_int(data.get("pcie_width"), strict),
            index=_int(data.get("index"), strict),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "vendor": self.vendor,
            "name": self.name,
            "vram_mb": self.vram_mb,
            "driver_version": self.driver_version,
            "compute_capability": self.compute_capability,
            "pcie_gen": self.pcie_gen,
            "pcie_width": self.pcie_width,
            "index": self.index,
        }


@dataclass
class TopologyInfo:
    """Hardware topology facts. Unavailable facts stay None."""

    numa_nodes: int | None = None
    sockets: int | None = None
    unified_memory: bool | None = None
    cpu_features: tuple[str, ...] = ()
    gpu_count: int | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any], strict: bool = False) -> TopologyInfo:
        features = data.get("cpu_features")
        unified = data.get("unified_memory")
        if strict and not isinstance(unified, (bool, type(None))):
            raise DomainParseError(f"expected a boolean, got {type(unified).__name__} {unified!r}")
        if strict and features is not None and not isinstance(features, list):
            raise DomainParseError(f"expected a list, got {type(features).__name__} {features!r}")
        return cls(
            numa_nodes=_int(data.get("numa_nodes"), strict),
            sockets=_int(data.get("sockets"), strict),
            unified_memory=unified if isinstance(unified, bool) else None,
            cpu_features=tuple(features) if isinstance(features, list) else (),
            gpu_count=_int(data.get("gpu_count"), strict),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "numa_nodes": self.numa_nodes,
            "sockets": self.sockets,
            "unified_memory": self.unified_memory,
            "cpu_features": list(self.cpu_features),
            "gpu_count": self.gpu_count,
        }


@dataclass
class SystemInfo:
    """Sanitized host description (no serials, MACs, usernames, paths)."""

    os: str | None = None
    os_version: str | None = None
    cpu: str | None = None
    cpu_cores_physical: int | None = None
    cpu_cores_logical: int | None = None
    gpu: str | None = None
    gpu_vram_mb: int | None = None
    gpu_driver_version: str | None = None
    npu: str | None = None
    ram_gb: float | None = None
    platform_name: str | None = None
    gpus: tuple[GpuInfo, ...] = ()
    topology: TopologyInfo = field(default_factory=TopologyInfo)

    @classmethod
    def from_dict(cls, data: dict[str, Any], strict: bool = False) -> SystemInfo:
        gpus_raw = data.get("gpus")
        gpus = (
            tuple(GpuInfo.from_dict(g, strict) for g in gpus_raw if isinstance(g, dict))
            if isinstance(gpus_raw, list)
            else ()
        )
        if strict and gpus_raw is not None and not isinstance(gpus_raw, list):
            raise DomainParseError(f"expected a list, got {type(gpus_raw).__name__} {gpus_raw!r}")
        topo_raw = data.get("topology")
        topology = (
            TopologyInfo.from_dict(topo_raw, strict)
            if isinstance(topo_raw, dict)
            else TopologyInfo()
        )
        if strict and topo_raw is not None and not isinstance(topo_raw, dict):
            raise DomainParseError(
                f"expected an object, got {type(topo_raw).__name__} {topo_raw!r}"
            )
        return cls(
            os=_str(data.get("os"), strict),
            os_version=_str(data.get("os_version"), strict),
            cpu=_str(data.get("cpu"), strict),
            cpu_cores_physical=_int(data.get("cpu_cores_physical"), strict),
            cpu_cores_logical=_int(data.get("cpu_cores_logical"), strict),
            gpu=_str(data.get("gpu"), strict),
            gpu_vram_mb=_int(data.get("gpu_vram_mb"), strict),
            gpu_driver_version=_str(data.get("gpu_driver_version"), strict),
            npu=_str(data.get("npu"), strict),
            ram_gb=_num(data.get("ram_gb"), strict),
            platform_name=_str(data.get("platform_name"), strict),
            gpus=gpus,
            topology=topology,
        )

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "os": self.os,
            "os_version": self.os_version,
            "cpu": self.cpu,
            "cpu_cores_physical": self.cpu_cores_physical,
            "cpu_cores_logical": self.cpu_cores_logical,
            "gpu": self.gpu,
            "gpu_vram_mb": self.gpu_vram_mb,
            "gpu_driver_version": self.gpu_driver_version,
            "npu": self.npu,
            "ram_gb": self.ram_gb,
            "platform_name": self.platform_name,
        }
        if self.gpus:
            out["gpus"] = [g.as_dict() for g in self.gpus]
        if self.topology != TopologyInfo():
            out["topology"] = self.topology.as_dict()
        return out


@dataclass
class RuntimeInfo:
    name: str | None = None
    version: str | None = None
    backend: str | None = None
    device: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any], strict: bool = False) -> RuntimeInfo:
        return cls(
            name=_str(data.get("name"), strict),
            version=_str(data.get("version"), strict),
            backend=_str(data.get("backend"), strict),
            device=_str(data.get("device"), strict),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "backend": self.backend,
            "device": self.device,
        }


@dataclass
class ModelInfo:
    name: str | None = None
    format: str | None = None
    quantization: str | None = None
    parameters: str | None = None
    checksum: str | None = None
    revision: str | None = None
    tokenizer: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any], strict: bool = False) -> ModelInfo:
        return cls(
            name=_str(data.get("name"), strict),
            format=_str(data.get("format"), strict),
            quantization=_str(data.get("quantization"), strict),
            parameters=_str(data.get("parameters"), strict),
            checksum=_str(data.get("checksum"), strict),
            revision=_str(data.get("revision"), strict),
            tokenizer=_str(data.get("tokenizer"), strict),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "format": self.format,
            "quantization": self.quantization,
            "parameters": self.parameters,
            "checksum": self.checksum,
            "revision": self.revision,
            "tokenizer": self.tokenizer,
        }


@dataclass
class WorkloadInfo:
    """Identity of the workload a result was measured with (schema 2.0)."""

    id: str | None = None
    version: str | None = None
    kind: str | None = None
    isl_tokens: int | None = None
    osl_tokens: int | None = None
    dataset: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any], strict: bool = False) -> WorkloadInfo:
        return cls(
            id=_str(data.get("id"), strict),
            version=_str(data.get("version"), strict),
            kind=_str(data.get("kind"), strict),
            isl_tokens=_int(data.get("isl_tokens"), strict),
            osl_tokens=_int(data.get("osl_tokens"), strict),
            dataset=_str(data.get("dataset"), strict),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "version": self.version,
            "kind": self.kind,
            "isl_tokens": self.isl_tokens,
            "osl_tokens": self.osl_tokens,
            "dataset": self.dataset,
        }


@dataclass
class MetricSet:
    """Measured metrics. ``None`` means "not measured" — never an estimate."""

    load_time_ms: float | None = None
    ttft_ms: float | None = None
    prompt_tokens_per_second: float | None = None
    generation_tokens_per_second: float | None = None
    total_latency_ms: float | None = None
    median_latency_ms: float | None = None
    p50_latency_ms: float | None = None
    p75_latency_ms: float | None = None
    p90_latency_ms: float | None = None
    p95_latency_ms: float | None = None
    p99_latency_ms: float | None = None
    p99_9_latency_ms: float | None = None
    min_latency_ms: float | None = None
    max_latency_ms: float | None = None
    stddev_latency_ms: float | None = None
    cv_latency: float | None = None
    ci95_latency_ms: tuple[float, float] | None = None
    tpot_ms: float | None = None
    itl_ms: float | None = None
    time_to_second_token_ms: float | None = None
    inter_chunk_latency_ms: float | None = None
    prefill_latency_ms: float | None = None
    decode_duration_ms: float | None = None
    queue_latency_ms: float | None = None
    request_latency_ms: float | None = None
    peak_ram_mb: float | None = None
    peak_vram_mb: float | None = None
    avg_cpu_util_percent: float | None = None
    avg_gpu_util_percent: float | None = None
    max_temperature_c: float | None = None
    average_power_watts: float | None = None
    idle_power_watts: float | None = None
    incremental_power_watts: float | None = None
    performance_per_watt: float | None = None
    throughput_inferences_per_second: float | None = None
    energy_joules_per_token: float | None = None
    energy_joules_per_request: float | None = None
    energy_joules_per_1k_tokens: float | None = None
    requests_per_second: float | None = None
    error_rate: float | None = None

    _NUMERIC_FIELDS = (
        "load_time_ms",
        "ttft_ms",
        "prompt_tokens_per_second",
        "generation_tokens_per_second",
        "total_latency_ms",
        "median_latency_ms",
        "p50_latency_ms",
        "p75_latency_ms",
        "p90_latency_ms",
        "p95_latency_ms",
        "p99_latency_ms",
        "p99_9_latency_ms",
        "min_latency_ms",
        "max_latency_ms",
        "stddev_latency_ms",
        "cv_latency",
        "tpot_ms",
        "itl_ms",
        "time_to_second_token_ms",
        "inter_chunk_latency_ms",
        "prefill_latency_ms",
        "decode_duration_ms",
        "queue_latency_ms",
        "request_latency_ms",
        "peak_ram_mb",
        "peak_vram_mb",
        "avg_cpu_util_percent",
        "avg_gpu_util_percent",
        "max_temperature_c",
        "average_power_watts",
        "idle_power_watts",
        "incremental_power_watts",
        "performance_per_watt",
        "throughput_inferences_per_second",
        "energy_joules_per_token",
        "energy_joules_per_request",
        "energy_joules_per_1k_tokens",
        "requests_per_second",
        "error_rate",
    )

    @classmethod
    def from_dict(cls, data: dict[str, Any], strict: bool = False) -> MetricSet:
        from .metrics import _MISSING, resolve_metric

        kwargs: dict[str, Any] = {}
        for name in cls._NUMERIC_FIELDS:
            resolved = resolve_metric(data, name)
            if resolved is not _MISSING:
                kwargs[name] = _num(resolved, strict)
        ci = resolve_metric(data, "ci95_latency_ms")
        if strict and ci is not _MISSING and not (isinstance(ci, (list, tuple)) and len(ci) == 2):
            raise DomainParseError(f"expected a 2-element array, got {ci!r}")
        kwargs["ci95_latency_ms"] = (
            (_num(ci[0], strict), _num(ci[1], strict))
            if isinstance(ci, (list, tuple)) and len(ci) == 2
            else None
        )
        return cls(**kwargs)

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {name: getattr(self, name) for name in self._NUMERIC_FIELDS}
        out["ci95_latency_ms"] = (
            list(self.ci95_latency_ms) if self.ci95_latency_ms is not None else None
        )
        # Drop trailing Nones? No: keep explicit nulls so consumers can
        # distinguish "not measured" from "absent".
        return out


@dataclass
class IterationSample:
    """One measured iteration/request sample."""

    ttft_ms: float | None = None
    total_latency_ms: float | None = None
    completion_tokens: int | None = None
    prompt_tokens: int | None = None
    eval_seconds: float | None = None
    prompt_eval_seconds: float | None = None
    tpot_ms: float | None = None
    prefill_latency_ms: float | None = None
    decode_duration_ms: float | None = None
    queue_latency_ms: float | None = None
    request_latency_ms: float | None = None
    success: bool | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any], strict: bool = False) -> IterationSample:
        known: dict[str, Any] = {
            "ttft_ms": _num(data.get("ttft_ms"), strict),
            "total_latency_ms": _num(data.get("total_latency_ms"), strict),
            "completion_tokens": _int(data.get("completion_tokens"), strict),
            "prompt_tokens": _int(data.get("prompt_tokens"), strict),
            "eval_seconds": _num(data.get("eval_seconds"), strict),
            "prompt_eval_seconds": _num(data.get("prompt_eval_seconds"), strict),
            "tpot_ms": _num(data.get("tpot_ms"), strict),
            "prefill_latency_ms": _num(data.get("prefill_latency_ms"), strict),
            "decode_duration_ms": _num(data.get("decode_duration_ms"), strict),
            "queue_latency_ms": _num(data.get("queue_latency_ms"), strict),
            "request_latency_ms": _num(data.get("request_latency_ms"), strict),
        }
        success_raw = data.get("success")
        if strict and success_raw is not None and not isinstance(success_raw, bool):
            raise DomainParseError(
                f"expected a boolean, got {type(success_raw).__name__} {success_raw!r}"
            )
        known["success"] = success_raw if isinstance(success_raw, bool) else None
        known["extra"] = {
            k: v for k, v in data.items() if k not in (*known.keys(), "success", "extra")
        }
        return cls(**known)

    def as_dict(self) -> dict[str, Any]:
        out = {
            "ttft_ms": self.ttft_ms,
            "total_latency_ms": self.total_latency_ms,
            "completion_tokens": self.completion_tokens,
            "prompt_tokens": self.prompt_tokens,
            "eval_seconds": self.eval_seconds,
            "prompt_eval_seconds": self.prompt_eval_seconds,
            "tpot_ms": self.tpot_ms,
            "prefill_latency_ms": self.prefill_latency_ms,
            "decode_duration_ms": self.decode_duration_ms,
            "queue_latency_ms": self.queue_latency_ms,
            "request_latency_ms": self.request_latency_ms,
            "success": self.success,
        }
        out.update(self.extra)
        return out


@dataclass
class TelemetrySummary:
    """Aggregated background telemetry samples."""

    peak_ram_mb: float | None = None
    peak_vram_mb: float | None = None
    avg_cpu_util_percent: float | None = None
    avg_gpu_util_percent: float | None = None
    max_temperature_c: float | None = None
    average_power_watts: float | None = None
    source: str | None = None
    interval_seconds: float | None = None
    samples: int | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any], strict: bool = False) -> TelemetrySummary:
        return cls(
            peak_ram_mb=_num(data.get("peak_ram_mb"), strict),
            peak_vram_mb=_num(data.get("peak_vram_mb"), strict),
            avg_cpu_util_percent=_num(data.get("avg_cpu_util_percent"), strict),
            avg_gpu_util_percent=_num(data.get("avg_gpu_util_percent"), strict),
            max_temperature_c=_num(data.get("max_temperature_c"), strict),
            average_power_watts=_num(data.get("average_power_watts"), strict),
            source=_str(data.get("source"), strict),
            interval_seconds=_num(data.get("interval_seconds"), strict),
            samples=_int(data.get("samples"), strict),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "peak_ram_mb": self.peak_ram_mb,
            "peak_vram_mb": self.peak_vram_mb,
            "avg_cpu_util_percent": self.avg_cpu_util_percent,
            "avg_gpu_util_percent": self.avg_gpu_util_percent,
            "max_temperature_c": self.max_temperature_c,
            "average_power_watts": self.average_power_watts,
            "source": self.source,
            "interval_seconds": self.interval_seconds,
            "samples": self.samples,
        }


@dataclass
class ReproducibilityInfo:
    prompt: str | None = None
    max_tokens: int | None = None
    temperature: float | None = None
    seed: int | None = None
    context_length: int | None = None
    warmup_runs: int | None = None
    iterations: int | None = None
    command: str | None = None
    python_version: str | None = None
    power_profile: str | None = None
    trust: str | None = None
    batch_size: int | None = None
    concurrency: int | None = None
    workload_type: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any], strict: bool = False) -> ReproducibilityInfo:
        temp = data.get("temperature")
        return cls(
            prompt=_str(data.get("prompt"), strict),
            max_tokens=_int(data.get("max_tokens"), strict),
            temperature=_num(temp, strict),
            seed=_int(data.get("seed"), strict),
            context_length=_int(data.get("context_length"), strict),
            warmup_runs=_int(data.get("warmup_runs"), strict),
            iterations=_int(data.get("iterations"), strict),
            command=_str(data.get("command"), strict),
            python_version=_str(data.get("python_version"), strict),
            power_profile=_str(data.get("power_profile"), strict),
            trust=_str(data.get("trust"), strict),
            batch_size=_int(data.get("batch_size"), strict),
            concurrency=_int(data.get("concurrency"), strict),
            workload_type=_str(data.get("workload_type"), strict),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "prompt": self.prompt,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "seed": self.seed,
            "context_length": self.context_length,
            "warmup_runs": self.warmup_runs,
            "iterations": self.iterations,
            "command": self.command,
            "python_version": self.python_version,
            "power_profile": self.power_profile,
            "trust": self.trust,
            "batch_size": self.batch_size,
            "concurrency": self.concurrency,
            "workload_type": self.workload_type,
        }


@dataclass
class ProvenanceInfo:
    """Hashes enabling tamper detection (schema 2.0)."""

    result_hash: str | None = None
    workload_hash: str | None = None
    environment_hash: str | None = None
    model_identity_hash: str | None = None
    hash_algorithm: str | None = None
    signature: str | None = None
    signature_provider: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any], strict: bool = False) -> ProvenanceInfo:
        return cls(
            result_hash=_str(data.get("result_hash"), strict),
            workload_hash=_str(data.get("workload_hash"), strict),
            environment_hash=_str(data.get("environment_hash"), strict),
            model_identity_hash=_str(data.get("model_identity_hash"), strict),
            hash_algorithm=_str(data.get("hash_algorithm"), strict),
            signature=_str(data.get("signature"), strict),
            signature_provider=_str(data.get("signature_provider"), strict),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "result_hash": self.result_hash,
            "workload_hash": self.workload_hash,
            "environment_hash": self.environment_hash,
            "model_identity_hash": self.model_identity_hash,
            "hash_algorithm": self.hash_algorithm,
            "signature": self.signature,
            "signature_provider": self.signature_provider,
        }


@dataclass
class BenchmarkResult:
    """A complete parsed benchmark result document."""

    run_id: str | None = None
    timestamp: str | None = None
    schema_version: str | None = None
    protocol_version: str | None = None
    system: SystemInfo = field(default_factory=SystemInfo)
    runtime: RuntimeInfo = field(default_factory=RuntimeInfo)
    model: ModelInfo = field(default_factory=ModelInfo)
    metrics: MetricSet = field(default_factory=MetricSet)
    reproducibility: ReproducibilityInfo = field(default_factory=ReproducibilityInfo)
    workload: WorkloadInfo | None = None
    provenance: ProvenanceInfo | None = None
    telemetry: TelemetrySummary | None = None
    iterations: tuple[IterationSample, ...] = ()
    git_commit: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any], strict: bool = False) -> BenchmarkResult:
        """Parse a result document.

        In lenient mode (default) wrong-typed fields become ``None`` so a
        single corrupt field degrades gracefully. In strict mode a wrong-typed
        field raises :class:`DomainParseError` — corrupt input is never
        silently disguised as "not measured". Genuine missing fields and
        explicit JSON ``null`` remain ``None`` in both modes.
        """
        if not isinstance(data, dict):
            raise TypeError("result document must be a JSON object")
        workload_raw = data.get("workload")
        prov_raw = data.get("provenance")
        tele_raw = data.get("telemetry") or data.get("telemetry_summary")
        iterations_raw = data.get("iterations")
        return cls(
            run_id=_str(data.get("run_id"), strict),
            timestamp=_str(data.get("timestamp"), strict),
            schema_version=_str(data.get("schema_version"), strict),
            protocol_version=_str(data.get("protocol_version"), strict),
            system=SystemInfo.from_dict(data.get("system") or {}, strict),
            runtime=RuntimeInfo.from_dict(data.get("runtime") or {}, strict),
            model=ModelInfo.from_dict(data.get("model") or {}, strict),
            metrics=MetricSet.from_dict(data.get("metrics") or {}, strict),
            reproducibility=ReproducibilityInfo.from_dict(
                data.get("reproducibility") or {}, strict
            ),
            workload=WorkloadInfo.from_dict(workload_raw, strict)
            if isinstance(workload_raw, dict)
            else None,
            provenance=(
                ProvenanceInfo.from_dict(prov_raw, strict) if isinstance(prov_raw, dict) else None
            ),
            telemetry=(
                TelemetrySummary.from_dict(tele_raw, strict) if isinstance(tele_raw, dict) else None
            ),
            iterations=tuple(
                IterationSample.from_dict(i, strict) for i in iterations_raw if isinstance(i, dict)
            )
            if isinstance(iterations_raw, list)
            else (),
            git_commit=_str(data.get("git_commit"), strict),
            raw=data,
        )

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "system": self.system.as_dict(),
            "runtime": self.runtime.as_dict(),
            "model": self.model.as_dict(),
            "metrics": self.metrics.as_dict(),
            "reproducibility": self.reproducibility.as_dict(),
        }
        if self.protocol_version:
            out["protocol_version"] = self.protocol_version
        if self.workload is not None:
            out["workload"] = self.workload.as_dict()
        if self.provenance is not None:
            out["provenance"] = self.provenance.as_dict()
        if self.telemetry is not None:
            out["telemetry"] = self.telemetry.as_dict()
        if self.iterations:
            out["iterations"] = [i.as_dict() for i in self.iterations]
        if self.git_commit:
            out["git_commit"] = self.git_commit
        return out
