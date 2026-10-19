"""Executive summary report (Markdown / HTML / PDF) and pre-publication review package builder.

Generates standalone executive summaries across one or more benchmark result
documents, detailed per-model Markdown reports enumerating all 54 canonical
metrics in ``METRIC_REGISTRY``, print-styled HTML/PDF reports, and shareable
``.zip`` review bundles for hardware evaluators and vendor review workflows.
"""

from __future__ import annotations

import html
import json
import os
import re
import shutil
import subprocess
import zipfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .export import comparison_groups, group_label
from .metrics import (
    METRIC_DESCRIPTIONS,
    METRIC_REGISTRY,
    performance_per_watt_unit,
)
from .report import _resolve_result_metric, render_detailed_report
from .sanitize import redact_object

__all__ = [
    "render_executive_summary_markdown",
    "render_executive_summary_html",
    "find_headless_browser",
    "compile_html_to_pdf",
    "build_review_package",
]


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip()).strip("-").lower()
    return slug or "result"


def _fmt_num(val: Any, decimals: int = 2, suffix: str = "") -> str:
    if val is None:
        return "not measured"
    if isinstance(val, float):
        return f"{val:,.{decimals}f}{suffix}"
    if isinstance(val, int) and not isinstance(val, bool):
        return f"{val:,}{suffix}"
    return f"{val}{suffix}"


def _primary_throughput(result: dict[str, Any]) -> tuple[float | None, str]:
    gen_tps = _resolve_result_metric(result, "generation_tokens_per_second")
    if isinstance(gen_tps, (int, float)) and gen_tps > 0:
        return float(gen_tps), "tok/s"
    inf_s = _resolve_result_metric(result, "throughput_inferences_per_second")
    if isinstance(inf_s, (int, float)) and inf_s > 0:
        return float(inf_s), "inf/s"
    return None, "tok/s"


def _summary_row(result: dict[str, Any]) -> dict[str, Any]:
    run_id = str(result.get("run_id") or "unknown")
    model = result.get("model") or {}
    runtime = result.get("runtime") or {}
    system = result.get("system") or {}
    metrics = result.get("metrics") or {}
    capacity = result.get("capacity") or {}
    thermal = result.get("thermal") or {}
    telemetry = result.get("telemetry") or {}

    model_name = str(model.get("name") or model.get("id") or run_id)
    runtime_name = str(runtime.get("name") or runtime.get("backend") or "unknown")
    quant = str(model.get("quantization") or model.get("precision") or model.get("format") or "n/a")
    device_label = str(
        system.get("gpu")
        or (system.get("npu", {}).get("card") if isinstance(system.get("npu"), dict) else system.get("npu"))
        or system.get("cpu")
        or runtime.get("device")
        or "unknown"
    )

    tput, tput_unit = _primary_throughput(result)
    ttft = _resolve_result_metric(result, "ttft_ms")
    prefill = _resolve_result_metric(result, "prompt_tokens_per_second")
    p50_lat = _resolve_result_metric(result, "p50_latency_ms") or _resolve_result_metric(
        result, "total_latency_ms"
    )
    pwr = _resolve_result_metric(result, "average_power_watts") or (
        telemetry.get("active_power_w") if isinstance(telemetry, dict) else None
    )
    idle_pwr = _resolve_result_metric(result, "idle_power_watts") or (
        telemetry.get("idle_power_w") if isinstance(telemetry, dict) else None
    )
    ppw = _resolve_result_metric(result, "performance_per_watt")
    ppw_unit = performance_per_watt_unit(metrics)

    net_ppw: float | None = None
    if (
        isinstance(tput, (int, float))
        and isinstance(pwr, (int, float))
        and isinstance(idle_pwr, (int, float))
        and (pwr - idle_pwr) > 0
    ):
        net_ppw = round(float(tput) / float(pwr - idle_pwr), 2)

    if ppw is None and isinstance(tput, (int, float)) and isinstance(pwr, (int, float)) and pwr > 0:
        ppw = round(float(tput) / float(pwr), 2)

    peak_temp = _resolve_result_metric(result, "max_temperature_c") or (
        thermal.get("peak_temperature_c") if isinstance(thermal, dict) else None
    )
    vram_mb = _resolve_result_metric(result, "peak_vram_mb") or (
        telemetry.get("hbm3_used_mb") if isinstance(telemetry, dict) else None
    )
    ram_mb = _resolve_result_metric(result, "peak_ram_mb")
    mem_mb = vram_mb if vram_mb is not None else ram_mb

    c64_tps = (
        capacity.get("peak_concurrency_tokens_per_second") if isinstance(capacity, dict) else None
    )

    return {
        "run_id": run_id,
        "slug": _slugify(run_id),
        "model_name": model_name,
        "runtime_name": runtime_name,
        "quant": quant,
        "device_label": device_label,
        "tput": tput,
        "tput_unit": tput_unit,
        "ttft": ttft,
        "prefill": prefill,
        "p50_lat": p50_lat,
        "c64_tps": c64_tps,
        "pwr": pwr,
        "ppw": ppw,
        "ppw_unit": ppw_unit,
        "net_ppw": net_ppw,
        "peak_temp": peak_temp,
        "mem_mb": mem_mb,
    }


_DEFAULT_CONFIDENTIAL_NOTICE = (
    "CONFIDENTIAL PRE-PUBLICATION REVIEW — Do not distribute or publish "
    "prior to hardware/runtime maintainer verification and sign-off."
)


def render_executive_summary_markdown(
    results: Sequence[dict[str, Any]],
    *,
    title: str = "AIHWBench Hardware Evaluation Report",
    subtitle: str | None = None,
    prepared_for: str | None = None,
    confidential_notice: str | None = None,
    confidential: bool = False,
) -> str:
    """Render a multi-model executive summary Markdown report."""
    rows = [_summary_row(r) for r in results]
    groups = comparison_groups(results) if results else []
    if confidential and not confidential_notice:
        confidential_notice = _DEFAULT_CONFIDENTIAL_NOTICE

    lines: list[str] = [f"# {title}", ""]
    if subtitle:
        lines.extend([f"**{subtitle}**", ""])

    if prepared_for or confidential_notice:
        lines.append("> [!IMPORTANT]")
        if prepared_for:
            lines.append(f"> **Prepared For:** {prepared_for}  ")
        if confidential_notice:
            lines.append(f"> {confidential_notice}")
        lines.append("")

    lines.extend(
        [
            "## Executive Summary",
            "",
            f"- **Evaluated Runs / Models:** {len(rows)}",
            f"- **Comparison-Safety Groups:** {len(groups)}",
        ]
    )

    if rows:
        devices = sorted({r["device_label"] for r in rows if r["device_label"]})
        runtimes = sorted({r["runtime_name"] for r in rows if r["runtime_name"]})
        lines.append(f"- **Hardware / Accelerator(s):** {', '.join(devices)}")
        lines.append(f"- **Runtime(s):** {', '.join(runtimes)}")

    lines.extend(
        [
            "",
            "---",
            "",
            "## Master Benchmark Summary Table",
            "",
            "| Run / Model | Runtime | Quant / Format | Primary Throughput | TTFT (ms) | Prompt (tok/s) | Latency p50 (ms) | Active Power | Perf / Watt | Peak Temp | Peak Memory |",
            "| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
        ]
    )

    for r in rows:
        tput_str = (
            f"**{r['tput']:,.2f} {r['tput_unit']}**"
            if isinstance(r["tput"], (int, float))
            else "not measured"
        )
        ttft_str = _fmt_num(r["ttft"], 2)
        prefill_str = _fmt_num(r["prefill"], 1)
        p50_str = _fmt_num(r["p50_lat"], 2)
        pwr_str = _fmt_num(r["pwr"], 1, " W")
        ppw_str = (
            f"**{r['ppw']:,.2f} {r['ppw_unit']}**"
            if isinstance(r["ppw"], (int, float))
            else "not measured"
        )
        temp_str = _fmt_num(r["peak_temp"], 1, " C")
        mem_str = _fmt_num(r["mem_mb"], 0, " MB")
        lines.append(
            f"| [`{r['model_name']}`](models/{r['slug']}.md) (`{r['run_id']}`) | `{r['runtime_name']}` | `{r['quant']}` | {tput_str} | {ttft_str} | {prefill_str} | {p50_str} | {pwr_str} | {ppw_str} | {temp_str} | {mem_str} |"
        )

    lines.extend(
        [
            "",
            "---",
            "",
            "## Comparison-Safety Grouping",
            "",
            "Results are partitioned by `aihwbench/comparability.py` so only mutually comparable runs share a group:",
            "",
        ]
    )
    for g in groups:
        label = group_label(g)
        member_ids = ", ".join(f"`{m.get('run_id', '?')}`" for m in g)
        lines.append(f"- **{label}** ({len(g)} run(s)): {member_ids}")

    lines.extend(
        [
            "",
            "---",
            "",
            "## Per-Model Detailed Reports (All 54 Canonical Metrics)",
            "",
            "Each model report in `models/` enumerates all 54 canonical metrics in `METRIC_REGISTRY`, hardware telemetry, energy, thermals, and iteration-by-iteration statistics:",
            "",
        ]
    )
    for r in rows:
        lines.append(
            f"- [`models/{r['slug']}.md`](models/{r['slug']}.md) — **{r['model_name']}** (`{r['run_id']}`)"
        )

    lines.extend(
        [
            "",
            "---",
            "",
            "## Complete 54-Metric Coverage Specification",
            "",
            "| # | Canonical Metric Key | Family | Unit | Measured Runs | Definition & Measurement Basis |",
            "| :---: | :--- | :--- | :---: | :---: | :--- |",
        ]
    )
    for idx, (key, meta) in enumerate(METRIC_REGISTRY.items(), start=1):
        fam = str(meta.get("family", "general")).capitalize()
        unit = str(meta.get("unit", ""))
        desc = METRIC_DESCRIPTIONS.get(key, key)
        measured_count = sum(1 for res in results if _resolve_result_metric(res, key) is not None)
        lines.append(
            f"| {idx} | `{key}` | {fam} | `{unit}` | {measured_count}/{len(results)} | {desc} |"
        )

    lines.append("")
    return "\n".join(lines)


def render_executive_summary_html(
    results: Sequence[dict[str, Any]],
    *,
    title: str = "AIHWBench Hardware Evaluation Report",
    subtitle: str | None = None,
    prepared_for: str | None = None,
    confidential_notice: str | None = None,
    confidential: bool = False,
    include_model_details: bool = True,
) -> str:
    """Render a standalone, print-styled HTML report suitable for PDF compilation."""
    if confidential and not confidential_notice:
        confidential_notice = _DEFAULT_CONFIDENTIAL_NOTICE
    rows = [_summary_row(r) for r in results]
    esc = html.escape

    devices = sorted({r["device_label"] for r in rows if r["device_label"]})
    runtimes = sorted({r["runtime_name"] for r in rows if r["runtime_name"]})
    device_summary = ", ".join(devices) if devices else "N/A"
    runtime_summary = ", ".join(runtimes) if runtimes else "N/A"

    # Compute highlight metrics
    valid_tputs = [r["tput"] for r in rows if isinstance(r["tput"], (int, float))]
    valid_ttfts = [r["ttft"] for r in rows if isinstance(r["ttft"], (int, float)) and r["ttft"] > 0]
    valid_ppws = [r["ppw"] for r in rows if isinstance(r["ppw"], (int, float))]
    valid_temps = [r["peak_temp"] for r in rows if isinstance(r["peak_temp"], (int, float))]

    max_tput = f"{max(valid_tputs):,.2f}" if valid_tputs else "N/A"
    min_ttft = f"{min(valid_ttfts):,.2f} ms" if valid_ttfts else "N/A"
    max_ppw = f"{max(valid_ppws):,.2f}" if valid_ppws else "N/A"
    max_temp = f"{max(valid_temps):,.1f} °C" if valid_temps else "N/A"

    sub_text = subtitle or "Standardized Local AI Hardware Benchmark & Full-Metric Evaluation"
    prep_text = prepared_for or "Open-Source Hardware Evaluation"

    callout_html = ""
    if confidential_notice:
        callout_html = f"""
        <div class="callout-box">
          <strong>Pre-Publication &amp; Confidentiality Notice:</strong> {esc(confidential_notice)}
        </div>
        """

    table_rows_html: list[str] = []
    for r in rows:
        tput_s = (
            f"{r['tput']:,.2f} {esc(r['tput_unit'])}"
            if isinstance(r["tput"], (int, float))
            else "not measured"
        )
        ttft_s = _fmt_num(r["ttft"], 2)
        prefill_s = _fmt_num(r["prefill"], 1)
        p50_s = _fmt_num(r["p50_lat"], 2)
        pwr_s = _fmt_num(r["pwr"], 1, " W")
        ppw_s = (
            f"{r['ppw']:,.2f} {esc(r['ppw_unit'])}"
            if isinstance(r["ppw"], (int, float))
            else "not measured"
        )
        temp_s = _fmt_num(r["peak_temp"], 1, " °C")
        mem_s = _fmt_num(r["mem_mb"], 0, " MB")
        table_rows_html.append(
            f"""
            <tr>
              <td class="bold">{esc(r['model_name'])}<br/><span style="font-size:7pt;color:#64748b;font-weight:400">{esc(r['run_id'])}</span></td>
              <td>{esc(r['runtime_name'])}</td>
              <td><span class="badge badge-primary">{esc(r['quant'])}</span></td>
              <td class="num highlight">{tput_s}</td>
              <td class="num">{esc(ttft_s)}</td>
              <td class="num">{esc(prefill_s)}</td>
              <td class="num">{esc(p50_s)}</td>
              <td class="num">{esc(pwr_s)}</td>
              <td class="num bold">{ppw_s}</td>
              <td class="num">{esc(temp_s)}</td>
              <td class="num">{esc(mem_s)}</td>
            </tr>
            """
        )

    details_html: list[str] = []
    if include_model_details:
        for res, r in zip(results, rows):
            metrics = res.get("metrics") or {}
            ppw_unit = performance_per_watt_unit(metrics)
            metric_rows_html: list[str] = []
            for idx, (key, meta) in enumerate(METRIC_REGISTRY.items(), start=1):
                fam = str(meta.get("family", "general")).capitalize()
                unit = ppw_unit if key == "performance_per_watt" else str(meta.get("unit", ""))
                desc = METRIC_DESCRIPTIONS.get(key, key)
                val = _resolve_result_metric(res, key)
                if val is None:
                    val_cell = '<span style="color:#94a3b8">not measured</span>'
                elif isinstance(val, float):
                    val_cell = f"<strong>{val:,.2f}</strong>" if abs(val) >= 10 else f"<strong>{val:,.4f}</strong>"
                elif isinstance(val, int) and not isinstance(val, bool):
                    val_cell = f"<strong>{val:,}</strong>"
                else:
                    val_cell = f"<strong>{esc(str(val))}</strong>"
                metric_rows_html.append(
                    f"""
                    <tr>
                      <td class="num">{idx}</td>
                      <td><code>{esc(key)}</code></td>
                      <td>{esc(fam)}</td>
                      <td class="num">{val_cell}</td>
                      <td><code>{esc(unit)}</code></td>
                      <td>{esc(desc)}</td>
                    </tr>
                    """
                )

            details_html.append(
                f"""
                <div class="model-section">
                  <h2>Model Report: {esc(r['model_name'])} <span style="font-size:9pt;color:#64748b;font-weight:400">({esc(r['run_id'])})</span></h2>
                  <p>Runtime: <code>{esc(r['runtime_name'])}</code> &bull; Device: <code>{esc(r['device_label'])}</code> &bull; Format/Quant: <code>{esc(r['quant'])}</code></p>
                  <table>
                    <thead>
                      <tr>
                        <th style="width:4%;text-align:right">#</th>
                        <th style="width:26%">Canonical Metric Key</th>
                        <th style="width:12%">Family</th>
                        <th style="width:14%;text-align:right">Measured Value</th>
                        <th style="width:10%">Unit</th>
                        <th style="width:34%">Definition &amp; Measurement Basis</th>
                      </tr>
                    </thead>
                    <tbody>
                      {''.join(metric_rows_html)}
                    </tbody>
                  </table>
                </div>
                """
            )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{esc(title)}</title>
<style>
  @page {{
    size: letter portrait;
    margin: 14mm 16mm 14mm 16mm;
  }}
  * {{
    box-sizing: border-box;
    margin: 0;
    padding: 0;
  }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    color: #1f2937;
    background: #ffffff;
    font-size: 9pt;
    line-height: 1.45;
  }}
  .header-card {{
    background: linear-gradient(135deg, #0f172a 0%, #1e293b 60%, #312e81 100%);
    color: #ffffff;
    padding: 20px 24px;
    border-radius: 8px;
    margin-bottom: 16px;
  }}
  .header-card h1 {{
    font-size: 18pt;
    font-weight: 700;
    letter-spacing: -0.02em;
    margin-bottom: 6px;
    color: #ffffff;
  }}
  .header-card .subtitle {{
    font-size: 10pt;
    color: #cbd5e1;
    margin-bottom: 12px;
  }}
  .meta-grid {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 10px;
    border-top: 1px solid rgba(255, 255, 255, 0.15);
    padding-top: 10px;
    font-size: 8pt;
  }}
  .meta-item .meta-label {{
    color: #94a3b8;
    text-transform: uppercase;
    font-size: 6.8pt;
    font-weight: 600;
    letter-spacing: 0.05em;
  }}
  .meta-item .meta-val {{
    color: #f8fafc;
    font-weight: 600;
    margin-top: 2px;
  }}
  h2 {{
    font-size: 12pt;
    font-weight: 700;
    color: #0f172a;
    border-bottom: 2px solid #e2e8f0;
    padding-bottom: 4px;
    margin-top: 16px;
    margin-bottom: 8px;
    page-break-after: avoid;
  }}
  p {{
    margin-bottom: 8px;
    color: #374151;
  }}
  .callout-box {{
    background: #f8fafc;
    border-left: 4px solid #4f46e5;
    padding: 10px 14px;
    border-radius: 4px;
    margin-bottom: 14px;
    font-size: 8.5pt;
  }}
  .badge {{
    display: inline-block;
    padding: 2px 6px;
    border-radius: 9999px;
    font-size: 7pt;
    font-weight: 600;
    text-transform: uppercase;
  }}
  .badge-primary {{ background: #e0e7ff; color: #4338ca; }}
  .key-metric-card-grid {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 10px;
    margin-bottom: 14px;
    page-break-inside: avoid;
  }}
  .metric-card {{
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    padding: 10px 12px;
    text-align: center;
  }}
  .metric-card .card-label {{
    font-size: 7pt;
    color: #64748b;
    text-transform: uppercase;
    font-weight: 600;
  }}
  .metric-card .card-value {{
    font-size: 14pt;
    font-weight: 800;
    color: #0f172a;
    margin-top: 2px;
  }}
  .metric-card .card-sub {{
    font-size: 7pt;
    color: #4f46e5;
    font-weight: 600;
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
    margin-bottom: 14px;
    font-size: 7.5pt;
  }}
  th {{
    background: #f1f5f9;
    color: #1e293b;
    font-weight: 700;
    text-align: left;
    padding: 5px 7px;
    border: 1px solid #cbd5e1;
    font-size: 7pt;
    text-transform: uppercase;
    letter-spacing: 0.02em;
  }}
  td {{
    padding: 4px 7px;
    border: 1px solid #e2e8f0;
    color: #334155;
  }}
  tr:nth-child(even) td {{
    background: #f8fafc;
  }}
  .num {{
    text-align: right;
    font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, Courier, monospace;
  }}
  .bold {{ font-weight: 700; color: #0f172a; }}
  .highlight {{ color: #4338ca; font-weight: 700; }}
  .model-section {{
    page-break-before: always;
  }}
  .footer {{
    margin-top: 18px;
    border-top: 1px solid #e2e8f0;
    padding-top: 8px;
    font-size: 7pt;
    color: #94a3b8;
    display: flex;
    justify-content: space-between;
  }}
</style>
</head>
<body>

<div class="header-card">
  <h1>{esc(title)}</h1>
  <div class="subtitle">{esc(sub_text)}</div>
  <div class="meta-grid">
    <div class="meta-item">
      <div class="meta-label">Prepared For</div>
      <div class="meta-val">{esc(prep_text)}</div>
    </div>
    <div class="meta-item">
      <div class="meta-label">Hardware / Device</div>
      <div class="meta-val">{esc(device_summary)}</div>
    </div>
    <div class="meta-item">
      <div class="meta-label">Runtime(s)</div>
      <div class="meta-val">{esc(runtime_summary)}</div>
    </div>
    <div class="meta-item">
      <div class="meta-label">Evaluated Runs</div>
      <div class="meta-val">{len(rows)} Verified Run(s)</div>
    </div>
  </div>
</div>

{callout_html}

<div class="key-metric-card-grid">
  <div class="metric-card">
    <div class="card-label">Peak Throughput</div>
    <div class="card-value">{esc(max_tput)}</div>
    <div class="card-sub">Across {len(rows)} evaluated run(s)</div>
  </div>
  <div class="metric-card">
    <div class="card-label">Lowest TTFT</div>
    <div class="card-value">{esc(min_ttft)}</div>
    <div class="card-sub">Time to First Token</div>
  </div>
  <div class="metric-card">
    <div class="card-label">Peak Perf / Watt</div>
    <div class="card-value">{esc(max_ppw)}</div>
    <div class="card-sub">Throughput per active Watt</div>
  </div>
  <div class="metric-card">
    <div class="card-label">Peak Die Temp</div>
    <div class="card-value">{esc(max_temp)}</div>
    <div class="card-sub">Measured thermal envelope</div>
  </div>
</div>

<h2>Master Benchmark Summary ({len(rows)} Evaluated Runs)</h2>
<p>All metrics below are directly measured. Unmeasured metrics on a platform are explicitly recorded as <code>not measured</code> and never estimated.</p>

<table>
  <thead>
    <tr>
      <th>Model / Run ID</th>
      <th>Runtime</th>
      <th>Quant / Format</th>
      <th style="text-align:right">Throughput</th>
      <th style="text-align:right">TTFT (ms)</th>
      <th style="text-align:right">Prompt (tok/s)</th>
      <th style="text-align:right">Latency p50 (ms)</th>
      <th style="text-align:right">Power</th>
      <th style="text-align:right">Perf / Watt</th>
      <th style="text-align:right">Peak Temp</th>
      <th style="text-align:right">Peak Memory</th>
    </tr>
  </thead>
  <tbody>
    {''.join(table_rows_html)}
  </tbody>
</table>

{''.join(details_html)}

<div class="footer">
  <div>Generated by AIHWBench (github.com/webdevsamran/local-ai-hardware-bench) &bull; All 54 Canonical Metrics</div>
  <div>Apache-2.0 &bull; Reproducible Local AI Hardware Benchmark</div>
</div>

</body>
</html>
"""


def find_headless_browser() -> str | None:
    """Locate an installed Chromium-based browser capable of `--print-to-pdf`."""
    candidates = [
        shutil.which("msedge"),
        shutil.which("google-chrome"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
        shutil.which("chrome"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "/usr/bin/google-chrome",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
    ]
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return None


def compile_html_to_pdf(
    html_path: Path,
    pdf_path: Path,
    *,
    timeout: float = 30.0,
) -> bool:
    """Compile an HTML file to PDF using headless Edge/Chrome/Chromium if available."""
    browser = find_headless_browser()
    if not browser:
        return False

    html_abs = html_path.resolve()
    pdf_abs = pdf_path.resolve()
    pdf_abs.parent.mkdir(parents=True, exist_ok=True)
    file_url = html_abs.as_uri()

    cmd = [
        browser,
        "--headless=new",
        "--disable-gpu",
        "--no-pdf-header-footer",
        f"--print-to-pdf={pdf_abs}",
        file_url,
    ]
    try:
        subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False

    return pdf_abs.is_file() and pdf_abs.stat().st_size > 0


def build_review_package(
    results_dir: Path,
    output_dir: Path,
    *,
    title: str = "AIHWBench Hardware Evaluation Report",
    subtitle: str | None = None,
    prepared_for: str | None = None,
    confidential_notice: str | None = None,
    confidential: bool = False,
    zip_path: Path | None = None,
    redact: bool = True,
) -> dict[str, Any]:
    """Build a complete multi-model evaluation & pre-publication review package.

    Writes:
    - ``<output_dir>/00_Executive_Summary_All_Models.md`` (Master Markdown summary)
    - ``<output_dir>/00_Executive_Summary_All_Models.html`` (Master styled HTML report)
    - ``<output_dir>/00_Executive_Summary_All_Models.pdf`` (Compiled PDF when Edge/Chrome/Chromium is present)
    - ``<output_dir>/models/<slug>.md`` (Per-run detailed report with all 54 canonical metrics)
    - ``<output_dir>/raw_results/<slug>.json`` (Redacted result JSON documents)
    - Optional ``zip_path`` bundling the entire directory for email attachment.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    models_dir = output_dir / "models"
    json_dir = output_dir / "raw_results"
    models_dir.mkdir(parents=True, exist_ok=True)
    json_dir.mkdir(parents=True, exist_ok=True)

    raw_results: list[dict[str, Any]] = []
    for p in sorted(results_dir.glob("*.json")):
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(doc, dict) and "metrics" in doc:
            raw_results.append(redact_object(doc) if redact else doc)

    if not raw_results:
        raise ValueError(f"no valid benchmark result JSON files found in {results_dir}")

    model_reports: list[str] = []
    json_files: list[str] = []
    for doc in raw_results:
        run_id = str(doc.get("run_id") or "result")
        slug = _slugify(run_id)
        md_file = models_dir / f"{slug}.md"
        md_file.write_text(render_detailed_report(doc), encoding="utf-8")
        model_reports.append(str(md_file))

        jf = json_dir / f"{slug}.json"
        jf.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
        json_files.append(str(jf))

    master_md_path = output_dir / "00_Executive_Summary_All_Models.md"
    master_md_path.write_text(
        render_executive_summary_markdown(
            raw_results,
            title=title,
            subtitle=subtitle,
            prepared_for=prepared_for,
            confidential_notice=confidential_notice,
            confidential=confidential,
        ),
        encoding="utf-8",
    )

    master_html_path = output_dir / "00_Executive_Summary_All_Models.html"
    master_html_path.write_text(
        render_executive_summary_html(
            raw_results,
            title=title,
            subtitle=subtitle,
            prepared_for=prepared_for,
            confidential_notice=confidential_notice,
            confidential=confidential,
            include_model_details=True,
        ),
        encoding="utf-8",
    )

    master_pdf_path = output_dir / "00_Executive_Summary_All_Models.pdf"
    pdf_compiled = bool(compile_html_to_pdf(master_html_path, master_pdf_path))

    zip_created: str | None = None
    if zip_path is not None:
        zip_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(output_dir):
                for file in sorted(files):
                    file_path = Path(root) / file
                    if file_path.resolve() == zip_path.resolve():
                        continue
                    arcname = file_path.relative_to(output_dir).as_posix()
                    zf.write(file_path, arcname=arcname)
        zip_created = str(zip_path)

    pdf_str = str(master_pdf_path) if pdf_compiled else None
    return {
        "model_count": len(raw_results),
        "results_count": len(raw_results),
        "output_dir": str(output_dir),
        "summary_markdown": str(master_md_path),
        "master_markdown": str(master_md_path),
        "summary_html": str(master_html_path),
        "master_html": str(master_html_path),
        "summary_pdf": pdf_str,
        "master_pdf": pdf_str,
        "pdf_compiled": pdf_compiled,
        "model_reports": model_reports,
        "json_files": json_files,
        "zip_path": zip_created,
        "zip_archive": zip_created,
    }
