"""Human-readable report generation from result documents.

Supports both concise single-run reports (``render_report(result)``) and
comprehensive full-metric reports (``render_report(result, full=True)`` or
``render_detailed_report(result)``) that enumerate all 54 canonical metrics in
``METRIC_REGISTRY`` alongside architecture metadata, telemetry, energy,
thermal, capacity, quality, and per-iteration statistical tables.
"""

from __future__ import annotations

from typing import Any

from .metrics import (
    _MISSING,
    METRIC_DESCRIPTIONS,
    METRIC_REGISTRY,
    performance_per_watt_unit,
    resolve_metric,
)
from .quality import statistical_confidence

NL = chr(10)

_METRIC_LABELS = [
    ("load_time_ms", "Model load time"),
    ("ttft_ms", "Time to first token"),
    ("prompt_tokens_per_second", "Prompt processing (tok/s)"),
    ("generation_tokens_per_second", "Generation (tok/s)"),
    ("total_latency_ms", "Total latency (mean)"),
    ("p50_latency_ms", "Latency p50"),
    ("p95_latency_ms", "Latency p95"),
    ("peak_ram_mb", "Peak RAM"),
    ("peak_vram_mb", "Peak VRAM"),
    ("avg_cpu_util_percent", "CPU utilization (avg)"),
    ("avg_gpu_util_percent", "GPU utilization (avg)"),
    ("max_temperature_c", "Max temperature"),
    ("average_power_watts", "Average power"),
    # performance_per_watt is appended separately: its unit depends on the
    # workload, so the label cannot be a constant.
]


def _fmt(value: Any, unit: str = "") -> str:
    if value is None:
        return "not measured"
    if isinstance(value, float):
        return f"{value:,.2f}{unit}"
    if isinstance(value, int) and not isinstance(value, bool):
        return f"{value:,}{unit}"
    return f"{value}{unit}"


def _resolve_result_metric(result: dict[str, Any], key: str) -> Any:
    """Resolve a canonical metric from `metrics` (or `energy` for published_in=energy)."""
    metrics = result.get("metrics") or {}
    val = resolve_metric(metrics, key)
    if val is not _MISSING and val is not None:
        return val
    meta = METRIC_REGISTRY.get(key) or {}
    if meta.get("published_in") == "energy":
        energy = result.get("energy") or {}
        if isinstance(energy, dict):
            for candidate in (key, "gross_joules_per_token", "incremental_joules_per_token"):
                if energy.get(candidate) is not None:
                    return energy[candidate]
    return None if val is _MISSING else val


def render_detailed_report(result: dict[str, Any]) -> str:
    """Render a full-detail markdown report listing all 54 canonical metrics."""
    system = result.get("system") or {}
    runtime = result.get("runtime") or {}
    model = result.get("model") or {}
    metrics = result.get("metrics") or {}
    repro = result.get("reproducibility") or {}
    workload = result.get("workload") or {}
    telemetry = result.get("telemetry") or {}
    energy = result.get("energy") or {}
    thermal = result.get("thermal") or {}
    capacity = result.get("capacity") or {}
    quality = result.get("quality") or {}
    iterations = result.get("iterations") or []

    run_id = result.get("run_id", "unknown")
    model_name = model.get("name") or model.get("id") or run_id
    runtime_name = runtime.get("name") or runtime.get("backend") or "unknown"

    lines: list[str] = [
        f"# Benchmark Evaluation Report: {model_name}",
        "",
        f"- **Run ID:** `{run_id}`",
        f"- **Timestamp:** {result.get('timestamp', 'unknown')}",
        f"- **Schema Version:** `{result.get('schema_version', '?')}`",
        f"- **Git Commit:** `{result.get('git_commit', 'unknown')}`",
        "",
        "## 1. Model & Architecture Metadata",
        "",
        "| Field | Specification |",
        "| :--- | :--- |",
        f"| **Model Name / ID** | `{_fmt(model.get('id') or model.get('name'))}` |",
        f"| **Format** | `{_fmt(model.get('format') or runtime.get('model_format'))}` |",
        f"| **Quantization / Precision** | `{_fmt(model.get('quantization') or model.get('precision'))}` |",
        f"| **Parameter Count** | {_fmt(model.get('parameters'))} |",
        f"| **Architecture / Family** | `{_fmt(model.get('architecture') or model.get('family'))}` |",
        f"| **License** | `{_fmt(model.get('license'))}` |",
        f"| **Checksum / Weights Digest** | `{_fmt(model.get('checksum') or model.get('weights_hash'))}` |",
    ]

    attention = model.get("attention")
    if isinstance(attention, dict) and attention:
        layers = attention.get("block_count") or attention.get("layers")
        heads = attention.get("head_count") or attention.get("heads")
        kv_heads = attention.get("head_count_kv") or attention.get("kv_heads")
        head_dim = attention.get("head_dim")
        ctx_len = attention.get("context_length")
        lines.append(f"| **Attention Layers** | {_fmt(layers)} |")
        lines.append(
            f"| **Attention Heads** | {_fmt(heads)} Q-heads / {_fmt(kv_heads)} KV-heads (head_dim: {_fmt(head_dim)}) |"
        )
        lines.append(f"| **Max Context Length** | {_fmt(ctx_len, ' tokens')} |")

    lines.extend(
        [
            "",
            "## 2. System & Runtime Profile",
            "",
            "| Component | Specification |",
            "| :--- | :--- |",
            f"| **Operating System** | {_fmt(system.get('os'))} ({_fmt(system.get('os_version'))}) |",
            f"| **Platform** | {_fmt(system.get('platform_name') or system.get('device'))} |",
            f"| **CPU** | {_fmt(system.get('cpu'))} ({_fmt(system.get('cpu_cores_physical') or system.get('cpu_cores'))} cores) |",
            f"| **GPU** | {_fmt(system.get('gpu'))} ({_fmt(system.get('gpu_vram_mb'), ' MB')}) |",
            f"| **NPU** | {_fmt(system.get('npu') or 'none detected')} |",
            f"| **System RAM** | {_fmt(system.get('ram_gb'), ' GB')} |",
            f"| **Runtime** | `{_fmt(runtime_name)}` ({_fmt(runtime.get('version'))}) |",
            f"| **Backend / Device** | `{_fmt(runtime.get('backend'))}` on `{_fmt(runtime.get('device') or system.get('device_type'))}` |",
            "",
            "## 3. Complete Metric Specification (All 54 Repository Metrics)",
            "",
            "The table below enumerates **100% of the canonical benchmark metrics** registered in `aihwbench.metrics.METRIC_REGISTRY`. Metrics that were not measured on this platform/workload are explicitly shown as `not measured` and never fabricated as zero:",
            "",
            "| # | Canonical Metric Key | Family | Measured Value | Unit | Definition & Measurement Basis |",
            "| :---: | :--- | :--- | :---: | :---: | :--- |",
        ]
    )

    ppw_unit = performance_per_watt_unit(metrics)
    for idx, (key, meta) in enumerate(METRIC_REGISTRY.items(), start=1):
        family = str(meta.get("family", "general")).capitalize()
        unit = ppw_unit if key == "performance_per_watt" else str(meta.get("unit", ""))
        desc = METRIC_DESCRIPTIONS.get(key, key.replace("_", " ").capitalize())
        val = _resolve_result_metric(result, key)
        if val is None:
            val_str = "not measured"
        elif isinstance(val, float):
            val_str = f"**{val:,.2f}**" if abs(val) >= 10 else f"**{val:,.4f}**"
        elif isinstance(val, int) and not isinstance(val, bool):
            val_str = f"**{val:,}**"
        else:
            val_str = f"**{val}**"
        lines.append(f"| {idx} | `{key}` | {family} | {val_str} | `{unit}` | {desc} |")

    if isinstance(capacity, dict) and capacity:
        lines.extend(
            [
                "",
                "## 4. Capacity & Concurrency Characteristics",
                "",
                "| Field | Value |",
                "| :--- | :--- |",
            ]
        )
        for k, v in capacity.items():
            lines.append(f"| `{k}` | {_fmt(v)} |")

    lines.extend(
        [
            "",
            "## 5. Hardware Telemetry, Energy & Thermal Breakdown",
            "",
            f"- **Idle Power Baseline:** {_fmt(_resolve_result_metric(result, 'idle_power_watts') or telemetry.get('idle_power_w'), ' W')}",
            f"- **Active Workload Power:** {_fmt(_resolve_result_metric(result, 'average_power_watts') or telemetry.get('active_power_w'), ' W')}",
            f"- **Net Incremental Power:** {_fmt(_resolve_result_metric(result, 'incremental_power_watts'), ' W')}",
            f"- **Peak Accelerator Temperature:** {_fmt(_resolve_result_metric(result, 'max_temperature_c') or thermal.get('peak_temperature_c'), ' C')}",
            f"- **Thermal Throttling Detected:** {_fmt(thermal.get('thermal_throttled') if isinstance(thermal, dict) else None)}",
            f"- **Energy per Token:** {_fmt(_resolve_result_metric(result, 'energy_joules_per_token'), ' J/token')}",
            f"- **Performance per Watt:** {_fmt(_resolve_result_metric(result, 'performance_per_watt'), f' {ppw_unit}')}",
        ]
    )
    if isinstance(energy, dict) and energy.get("basis"):
        lines.append(f"- **Energy Measurement Basis:** {energy.get('basis')}")

    conf = result.get("statistical_confidence")
    if not isinstance(conf, dict):
        conf = statistical_confidence(result)
    lines.extend(
        [
            "",
            "## 6. Statistical Rigor & Iterations",
            "",
            f"- **Policy Status:** `{conf.get('label', 'compliant')}` (meets publication policy: `{conf.get('meets_policy', False)}`)",
            f"- **Warm-up Runs:** {_fmt(repro.get('warmup_runs') or conf.get('warmup_count'))}",
            f"- **Measured Iterations:** {_fmt(repro.get('iterations') or conf.get('iterations_count') or (len(iterations) if isinstance(iterations, list) else None))}",
            f"- **Latency CV:** {_fmt(_resolve_result_metric(result, 'cv_latency'))}",
            f"- **Latency 95% CI:** {_fmt(_resolve_result_metric(result, 'ci95_latency_ms'), ' ms')}",
        ]
    )

    if isinstance(iterations, list) and iterations:
        lines.extend(
            [
                "",
                "| Iteration | Total Latency (ms) | TTFT (ms) | Throughput (tok/s) |",
                "| :---: | :---: | :---: | :---: |",
            ]
        )
        for i, it in enumerate(iterations, start=1):
            if not isinstance(it, dict):
                continue
            lat = it.get("total_latency_ms") if it.get("total_latency_ms") is not None else it.get("latency_ms")
            ttft_i = it.get("ttft_ms")
            tps_i = it.get("generation_tokens_per_second") or it.get("tokens_per_second")
            lines.append(
                f"| {it.get('iteration', i)} | {_fmt(lat)} | {_fmt(ttft_i)} | {_fmt(tps_i)} |"
            )

    if isinstance(quality, dict) and quality:
        lines.extend(
            [
                "",
                "## 7. Quality & Determinism Signals",
                "",
            ]
        )
        if quality.get("output_hash"):
            lines.append(f"- **Output Hash:** `{quality.get('output_hash')}`")
        if quality.get("deterministic") is not None:
            lines.append(f"- **Deterministic:** `{quality.get('deterministic')}`")
        evaluators = quality.get("evaluators")
        if isinstance(evaluators, dict) and evaluators:
            lines.extend(
                [
                    "",
                    "| Evaluator | Score | Status |",
                    "| :--- | :---: | :---: |",
                ]
            )
            for ev_name, ev_data in evaluators.items():
                if isinstance(ev_data, dict):
                    lines.append(
                        f"| `{ev_name}` | {_fmt(ev_data.get('score'))} | `{ev_data.get('status', 'n/a')}` |"
                    )

    lines.extend(
        [
            "",
            "## 8. Reproducibility",
            "",
            "```text",
            str(repro.get("command", "see documentation")),
            "```",
            "",
            f"- **Prompt / Suite:** {repro.get('prompt') or workload.get('suite') or 'n/a'!r}",
            f"- **Max / Output Tokens:** {repro.get('max_tokens') or workload.get('output_tokens', 'n/a')}, "
            f"**Temperature:** {repro.get('temperature', workload.get('temperature', 'n/a'))}, "
            f"**Seed:** {repro.get('seed', 'n/a')}",
            f"- **Context Length:** {repro.get('context_length') or model.get('context_length', 'n/a')}",
            "",
            "> Metrics reported as 'not measured' could not be captured reliably "
            "on this platform; they are never estimated.",
        ]
    )
    return NL.join(lines)


def render_report(result: dict[str, Any], *, full: bool = False) -> str:
    """Render a markdown report for one benchmark result.

    When ``full=True``, renders the comprehensive 54-metric report via
    ``render_detailed_report(result)``.
    """
    if full:
        return render_detailed_report(result)

    system = result.get("system", {})
    runtime = result.get("runtime", {})
    model = result.get("model", {})
    metrics = result.get("metrics", {})
    repro = result.get("reproducibility", {})

    lines: list[str] = []
    lines.append(f"# Benchmark Report - {result.get('run_id', 'unknown')}")
    lines.append("")
    lines.append(f"- **Timestamp:** {result.get('timestamp', 'unknown')}")
    lines.append(f"- **Schema:** {result.get('schema_version', '?')}")
    lines.append(f"- **Git commit:** `{result.get('git_commit', 'unknown')}`")
    lines.append("")
    lines.append("## System")
    lines.append("")
    lines.append(f"- **OS:** {_fmt(system.get('os'))} ({_fmt(system.get('os_version'))})")
    lines.append(f"- **Platform:** {_fmt(system.get('platform_name'))}")
    lines.append(
        f"- **CPU:** {_fmt(system.get('cpu'))} "
        f"({_fmt(system.get('cpu_cores_physical'))}C/"
        f"{_fmt(system.get('cpu_cores_logical'))}T)"
    )
    lines.append(
        f"- **GPU:** {_fmt(system.get('gpu'))} ({_fmt(system.get('gpu_vram_mb'), ' MB')} VRAM)"
    )
    npu = system.get("npu") or "none detected"
    lines.append(f"- **NPU:** {npu}")
    lines.append(f"- **RAM:** {_fmt(system.get('ram_gb'), ' GB')}")
    lines.append("")
    lines.append("## Runtime & Model")
    lines.append("")
    lines.append(f"- **Runtime:** {_fmt(runtime.get('name'))} {_fmt(runtime.get('version'))}")
    lines.append(f"- **Backend:** {_fmt(runtime.get('backend'))} on {_fmt(runtime.get('device'))}")
    lines.append(
        f"- **Model:** {_fmt(model.get('name'))} "
        f"(format: {_fmt(model.get('format'))}, quantization: {_fmt(model.get('quantization'))})"
    )
    checksum = model.get("checksum")
    if checksum:
        lines.append(f"- **Checksum:** `{checksum}`")
    lines.append("")
    lines.append("## Metrics")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("| --- | --- |")
    for key, label in _METRIC_LABELS:
        unit = ""
        if key.endswith("_ms"):
            unit = " ms"
        elif key.endswith("_mb"):
            unit = " MB"
        elif key.endswith("_c"):
            unit = " C"
        elif key.endswith("_watts"):
            unit = " W"
        elif key.endswith("_percent"):
            unit = "%"
        value = metrics.get(key)
        if value is None:
            rendered = "not measured"
        elif isinstance(value, float):
            rendered = f"{value:,.2f}{unit}"
        else:
            rendered = f"{value}{unit}"
        lines.append(f"| {label} | {rendered} |")
    # Rendered outside the table above because its unit is workload-dependent:
    # tok/s/W for generative runtimes, inf/s/W for graph/vision ones. A run
    # that produced zero tokens must never be labelled "tok/s/W".
    ppw = metrics.get("performance_per_watt")
    ppw_unit = performance_per_watt_unit(metrics)
    ppw_rendered = "not measured" if ppw is None else f"{ppw:,.2f} {ppw_unit}"
    lines.append(f"| Performance per watt | {ppw_rendered} |")
    lines.append("")
    lines.append("## Reproducibility")
    lines.append("")
    lines.append("```text")
    lines.append(str(repro.get("command", "see documentation")))
    lines.append("```")
    lines.append("")
    lines.append(f"- Prompt: {repro.get('prompt', 'n/a')!r}")
    lines.append(
        f"- Max tokens: {repro.get('max_tokens', 'n/a')}, "
        f"temperature: {repro.get('temperature', 'n/a')}, seed: {repro.get('seed', 'n/a')}"
    )
    lines.append(
        f"- Context length: {repro.get('context_length', 'n/a')}, "
        f"warm-up runs: {repro.get('warmup_runs', 'n/a')}, "
        f"measured iterations: {repro.get('iterations', 'n/a')}"
    )
    lines.append("")
    lines.append(
        "> Metrics reported as 'not measured' could not be captured reliably "
        "on this platform; they are never estimated."
    )
    return NL.join(lines)


def write_report(result: dict[str, Any], path: Any, *, full: bool = False) -> Any:
    """Write a markdown report to a path."""
    path.write_text(render_report(result, full=full), encoding="utf-8")
    return path

