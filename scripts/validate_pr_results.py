"""Validate benchmark results submitted in a pull request and render a report.

Usage:
    python scripts/validate_pr_results.py <result.json> [...] --output report.md

Exits 1 when any submission is not publishable, 0 otherwise.

This lives in a script rather than inside the workflow YAML so it can be
tested. Validation logic embedded in a workflow is only ever exercised by
opening a pull request, which is a slow and public way to find out that the
validator itself is broken.

What blocks a merge is deliberately narrow: schema errors, privacy findings
and impossible values. Everything else — an under-measured run, a result
comparable with nothing yet — is reported and merged. Losing a real
measurement from someone whose hardware cannot sit through a long run is a
worse outcome than publishing it with a label.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aihwbench.comparability import NOT_COMPARABLE, compare_classification  # noqa: E402
from aihwbench.plausibility import check_plausibility  # noqa: E402
from aihwbench.quality import data_quality_report, statistical_confidence  # noqa: E402
from aihwbench.sanitize import scan_object  # noqa: E402
from aihwbench.schemas import validate_result  # noqa: E402
from aihwbench.trust import effective_trust  # noqa: E402

NL = chr(10)


def _formal_errors(data: dict) -> list[str]:
    """Formal-schema errors, or a stated inability to check them.

    A missing `jsonschema` must not read as a clean bill of health.
    """
    try:
        from aihwbench.formal_schema import validate_formal

        return validate_formal(data)
    except RuntimeError as exc:
        return [f"formal validation unavailable: {exc}"]


def review_result(path: pathlib.Path) -> dict:
    """Everything worth saying about one submitted result."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"path": path, "readable": False, "error": str(exc), "blocking": True}

    schema_errors = validate_result(data) + _formal_errors(data)
    clean, privacy = scan_object(data)
    implausible = check_plausibility(data)

    return {
        "path": path,
        "readable": True,
        "data": data,
        "schema_errors": schema_errors,
        "privacy": privacy,
        "implausible": implausible,
        "confidence": statistical_confidence(data),
        "quality": data_quality_report(data),
        "trust": effective_trust(data),
        # Narrow on purpose: a wrong schema, a leaked identifier, or a value
        # that cannot be true. Not "this looks slow".
        "blocking": bool(schema_errors) or not clean or bool(implausible),
    }


def comparable_count(data: dict, published: list[pathlib.Path], exclude: pathlib.Path) -> int:
    """How many published results this submission may be compared against."""
    count = 0
    for candidate in published:
        if candidate.resolve() == exclude.resolve():
            continue
        try:
            other = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if compare_classification(data, other)["classification"] != NOT_COMPARABLE:
            count += 1
    return count


def render(reviews: list[dict], published: list[pathlib.Path]) -> str:
    lines = ["## Benchmark result validation", ""]
    if not reviews:
        lines.append("No result files changed in this pull request.")
        return NL.join(lines) + NL

    lines.append(f"Checked **{len(reviews)}** submitted result file(s).")
    lines.append("")

    for review in reviews:
        name = review["path"].as_posix()
        if not review["readable"]:
            lines += [f"### ❌ `{name}`", "", f"- **Unreadable**: {review['error']}", ""]
            continue

        mark = "❌" if review["blocking"] else "✅"
        quality = review["quality"]
        confidence = review["confidence"]
        lines += [
            f"### {mark} `{name}`",
            "",
            f"- Trust state on submission: `{review['trust']}`",
            f"- Statistical confidence: `{confidence['label']}` — {confidence['detail']}",
            f"- Quality checks passed: {quality['checks_passed']}/{quality['checks_total']}",
        ]
        if review["schema_errors"]:
            lines.append("- **Schema errors** (these block):")
            lines += [f"  - `{e}`" for e in review["schema_errors"][:10]]
        if review["privacy"]:
            # Findings arrive already redacted; the raw value is never echoed
            # into a public comment.
            lines.append("- **Privacy findings** (these block):")
            lines += [f"  - {p}" for p in review["privacy"][:10]]
        if review["implausible"]:
            lines.append("- **Impossible or inconsistent values** (these block):")
            lines += [f"  - `{f['field']}`: {f['detail']}" for f in review["implausible"][:10]]
        if not confidence["meets_policy"]:
            lines.append(
                "- Note: below the published statistical policy. This does not "
                "block; the result will be labelled in the leaderboard."
            )
        lines.append("")

    readable = [r for r in reviews if r["readable"]]
    if readable and published:
        lines += ["### Comparability with the existing dataset", ""]
        for review in readable:
            count = comparable_count(review["data"], published, review["path"])
            lines.append(
                f"- `{review['path'].name}`: comparable with "
                + (f"{count} published result(s)" if count else "**nothing yet**")
            )
        lines += [
            "",
            "Comparable with nothing is not a defect — it is what a genuinely "
            "new hardware or runtime combination looks like.",
            "",
        ]

    lines.append(
        "> Schema errors, privacy findings and impossible values block a merge. "
        "Everything else is information. See the "
        "[comparability rubric](docs/comparability-rubric.md) and the "
        "[dispute process](docs/disputes.md)."
    )
    return NL.join(lines) + NL


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", nargs="*", help="Submitted result JSON files")
    parser.add_argument("--output", default=None, help="Write the Markdown report here")
    parser.add_argument("--published-dir", default="results/published")
    args = parser.parse_args(argv)

    reviews = [review_result(pathlib.Path(p)) for p in args.results]
    published = sorted(pathlib.Path(args.published_dir).glob("*.json"))
    report = render(reviews, published)

    if args.output:
        pathlib.Path(args.output).write_text(report, encoding="utf-8")

    # The report contains status marks outside cp1252, and this project's own
    # reference machine is Windows. Printing it through a legacy console
    # encoding would crash the validator on exactly the platform most
    # contributors will run it from.
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except (AttributeError, OSError):  # pragma: no cover - exotic stdout
        pass
    print(report)

    blocking = sum(1 for r in reviews if r["blocking"])
    if blocking:
        print(f"{blocking} submitted result(s) are not publishable", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
