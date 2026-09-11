"""The accessibility gate has to run, fail, and say what it did not check.

An axe script that exists, works, and is never invoked by CI is the same
non-event as no script at all -- and it is worse than none, because the
repository then looks audited. So these tests check the wiring as carefully as
the behaviour: the npm script exists, CI calls it, and it calls it *after* the
build, since it reads `dist/`.

The third thing checked here is the honest-reporting rule. jsdom has no layout
engine, so `color-contrast` cannot return a verdict and comes back incomplete.
A run that quietly dropped incomplete results would print "no violations" and
mean "no violations among the rules that could run" -- which is the shape of
every false all-clear. The script has to name what it could not decide.

The finding that produced all this: the nine prerendered embed pages had no
`<main>` and no `<h1>`. The embed shell drops the site chrome deliberately,
because the card sits inside someone else's article -- but it dropped the
landmark and the heading with it, and an iframe is its own document, so a
screen reader entering one inherited no structure at all.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

WEB = Path("web")
SCRIPT = WEB / "scripts" / "a11y.mjs"
PACKAGE_JSON = WEB / "package.json"
CI = Path(".github/workflows/ci.yml")
EMBED = WEB / "src" / "pages" / "EmbedResult.tsx"
STYLES = WEB / "src" / "styles.css"


@pytest.fixture(scope="module")
def script() -> str:
    return SCRIPT.read_text(encoding="utf-8")


# --- the gate is wired ------------------------------------------------------


def test_the_script_exists():
    assert SCRIPT.is_file(), "the a11y gate is referenced but not present"


def test_npm_exposes_it():
    scripts = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))["scripts"]
    assert scripts.get("a11y") == "node scripts/a11y.mjs"


def test_axe_is_a_declared_dependency():
    """Installed-but-undeclared works locally and fails on a clean `npm ci`."""
    package = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    assert "axe-core" in package.get("devDependencies", {})


def test_ci_runs_the_gate():
    """Built, tested, and never called is this repository's commonest defect."""
    assert "npm run a11y" in CI.read_text(encoding="utf-8"), (
        "the a11y gate is not invoked by CI, so a regression reaches production silently"
    )


def test_ci_runs_the_gate_after_the_build():
    """It reads `dist/`. Run before the build it checks the previous artifact,
    or nothing at all, and passes either way."""
    ci = CI.read_text(encoding="utf-8")
    build = ci.index("npm run build")
    a11y = ci.index("npm run a11y")
    assert build < a11y, "the a11y step runs before the build, so it inspects a stale dist/"


# --- the gate can fail ------------------------------------------------------


def test_a_violation_fails_the_process(script):
    """Reporting a violation on stdout and exiting 0 is a passing CI job."""
    assert "process.exit(total === 0 ? 0 : 1)" in script


def test_an_empty_dist_is_an_error_not_a_pass(script):
    """Zero pages yields zero violations, which would read as a clean run."""
    assert "No HTML under" in script
    assert "process.exit(2)" in script


# --- the gate says what it could not check ----------------------------------


def test_undecidable_rules_are_reported_rather_than_dropped(script):
    """ "We did not look" and "we looked and it was fine" are different claims."""
    assert "Not evaluated" in script
    assert "unchecked by this run, not passing" in script


def test_it_points_at_where_contrast_is_actually_checked(script):
    """An unchecked rule with nowhere to look next is just an excuse."""
    assert "test_heatmap_contrast.py" in script


def test_rules_that_do_not_need_layout_are_checked_rather_than_excused(script):
    """`landmark-one-main` and `page-has-heading-one` error under jsdom and
    need no layout engine at all. Both are decidable from the DOM, so they are
    checked directly instead of being written off as unevaluable -- which is
    how the embed pages' missing landmark was found in the first place."""
    assert "STRUCTURAL_CHECKS" in script
    for rule in ("landmark-one-main", "page-has-heading-one"):
        assert rule in script


# --- the finding it produced ------------------------------------------------


def test_the_embed_card_is_a_landmark(script):
    """Every branch, not only the one with data.

    A `<div>` here is content belonging to no landmark, which is what `region`
    reported across all nine embed pages.
    """
    source = EMBED.read_text(encoding="utf-8")
    assert '<div className="embed-card' not in source, (
        "an embed branch renders a plain div, so its content sits outside any landmark"
    )
    # Every branch the component itself returns, so a branch added later
    # without a landmark shows up here rather than only in a build that
    # happens to prerender it. Indentation separates the component's own
    # returns from the ones inside the metric `.map()` callback.
    lines = source.splitlines()
    branches = []
    for i, line in enumerate(lines):
        if not re.match(r"^ {2,4}(?:if \(.*\) )?return\b", line):
            continue
        rest = line.split("return", 1)[1].strip().lstrip("(").strip()
        branches.append(rest or next(x.strip() for x in lines[i + 1 :] if x.strip()))
    assert len(branches) == 4, f"expected four embed branches, found {len(branches)}"
    assert all(b.startswith("<main") for b in branches), (
        f"an embed branch returns something that is not a main landmark: {branches}"
    )


def test_the_embed_card_names_itself_with_a_heading():
    source = EMBED.read_text(encoding="utf-8")
    assert '<h1 className="embed-model">' in source, (
        "the embed card has no h1, so a reader entering the iframe gets no heading outline"
    )


def test_the_heading_did_not_become_a_layout_change():
    """The global h1 scale is several times the 14px this card sets, and the
    browser's own h1 margin would push the metrics down. An accessibility fix
    that visibly redesigns the widget gets reverted by whoever notices."""
    css = STYLES.read_text(encoding="utf-8")
    block = re.search(r"\.embed-model\s*\{(.*?)\}", css, re.S)
    assert block is not None, ".embed-model has no rule, so the h1 takes the global heading size"
    body = block.group(1)
    assert "font-size: inherit" in body
    assert re.search(r"margin:\s*0", body)
