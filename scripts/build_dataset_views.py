"""Build static dataset views (JSON/CSV/Markdown/HTML) from published results.

Usage: python scripts/build_dataset_views.py <results_dir> <output_dir>

Stdlib-only. Regenerates everything from canonical result files - no
hand-maintained duplicates.
"""

from __future__ import annotations

import html
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aihwbench.export import export_dataset, load_results  # noqa: E402

NL = chr(10)


def _get(result: dict, *path: str) -> object:
    cur: object = result
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def fmt(value: object) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:,.2f}"
    return str(value)


def build_markdown(results: list[dict]) -> str:
    rows = [
        "| Runtime | Model | Device | Gen tok/s | TTFT ms | p95 latency ms | tok/s/W | Trust |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in results:
        rows.append(
            "| {runtime} | {model} | {device} | {tps} | {ttft} | {p95} | {ppw} | {trust} |".format(
                runtime=fmt(_get(r, "runtime", "name")),
                model=fmt(_get(r, "model", "name")),
                device=fmt(_get(r, "runtime", "device")),
                tps=fmt(_get(r, "metrics", "generation_tokens_per_second")),
                ttft=fmt(_get(r, "metrics", "ttft_ms")),
                p95=fmt(_get(r, "metrics", "p95_latency_ms")),
                ppw=fmt(_get(r, "metrics", "performance_per_watt")),
                trust=fmt(_get(r, "reproducibility", "trust")),
            )
        )
    header = (
        "# AIHWBench Dataset"
        + NL
        + NL
        + "Generated from validated results in `results/published/` - do not edit by hand."
        + NL
        + NL
        + "Trust states: VERIFIED / COMMUNITY_VALIDATED / UNVERIFIED."
        + NL
        + NL
    )
    return header + NL.join(rows) + NL


def build_html(results: list[dict]) -> str:
    body_rows = []
    for r in results:
        cells = [
            fmt(_get(r, "runtime", "name")),
            fmt(_get(r, "model", "name")),
            fmt(_get(r, "runtime", "device")),
            fmt(_get(r, "metrics", "generation_tokens_per_second")),
            fmt(_get(r, "metrics", "ttft_ms")),
            fmt(_get(r, "metrics", "p95_latency_ms")),
            fmt(_get(r, "metrics", "performance_per_watt")),
            fmt(_get(r, "reproducibility", "trust")),
        ]
        body_rows.append("<tr>" + "".join(f"<td>{html.escape(c)}</td>" for c in cells) + "</tr>")
    head = [
        "Runtime",
        "Model",
        "Device",
        "Gen tok/s",
        "TTFT ms",
        "p95 latency ms",
        "tok/s/W",
        "Trust",
    ]
    parts = [
        "<!doctype html><html><head><meta charset='utf-8'>",
        "<title>AIHWBench Dataset</title>",
        "<style>body{font-family:system-ui;margin:2rem}table{border-collapse:collapse}",
        "th,td{border:1px solid #ccc;padding:.4rem .6rem;text-align:left}",
        "th{background:#f4f4f4}</style></head><body>",
        "<h1>AIHWBench Dataset</h1>",
        "<p>Vendor-neutral local AI hardware benchmark results. ",
        "Generated from validated published results; unavailable metrics shown as -.</p>",
        "<table><thead><tr>" + "".join(f"<th>{h}</th>" for h in head),
        "</tr></thead><tbody>" + "".join(body_rows) + "</tbody></table>",
        "</body></html>",
    ]
    return "".join(parts) + NL


def main() -> None:
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    results_dir = pathlib.Path(sys.argv[1])
    output_dir = pathlib.Path(sys.argv[2])
    output_dir.mkdir(parents=True, exist_ok=True)

    written = export_dataset(results_dir, output_dir)
    for p in written:
        print(f"wrote {p}")

    results = load_results(results_dir)
    md_path = output_dir / "LEADERBOARD.md"
    md_path.write_text(build_markdown(results), encoding="utf-8")
    print(f"wrote {md_path}")
    html_path = output_dir / "index.html"
    html_path.write_text(build_html(results), encoding="utf-8")
    print(f"wrote {html_path}")


if __name__ == "__main__":
    main()
