"""Human-readable report generation from result documents."""

from __future__ import annotations

from typing import Any

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
    ("performance_per_watt", "Performance per watt (tok/s/W)"),
]


def _fmt(value: Any, unit: str = "") -> str:
    if value is None:
        return "not measured"
    if isinstance(value, float):
        return f"{value:,.2f}{unit}"
    if isinstance(value, int) and not isinstance(value, bool):
        return f"{value:,}{unit}"
    return f"{value}{unit}"


def render_report(result: dict[str, Any]) -> str:
    """Render a markdown report for one benchmark result."""
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


def write_report(result: dict[str, Any], path: Any) -> Any:
    """Write a markdown report to a path."""
    path.write_text(render_report(result), encoding="utf-8")
    return path
