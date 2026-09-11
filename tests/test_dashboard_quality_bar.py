"""The dashboard's stated quality bar, asserted rather than remembered.

These are the requirements from the plan's Part 4 that have no other test:
reduced motion, more contrast, print, fluid type, touch targets. Each is a
preference a real person set on their own machine, and each is the kind of
thing that works on the day it ships and quietly stops working six commits
later when somebody adds an animation or a colour.

The reduced-motion rule is the clearest case. It used to name the animations
it stopped, one at a time, which meant every new animation shipped moving
until someone remembered to add it -- and the person who needed it stopped was
the last to find out. It is a blanket rule now, and this test is what keeps it
one.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

STYLES = Path("web/src/styles.css")

#: The project's own bar. WCAG 2.2 AA requires 24x24; 44 is the AAA figure
#: and the one every mobile guideline converges on.
MINIMUM_TARGET_PX = 44.0


@pytest.fixture(scope="module")
def css() -> str:
    return STYLES.read_text(encoding="utf-8")


def _media_block(source: str, query: str) -> str:
    start = source.index(query)
    depth, i = 0, source.index("{", start)
    for j in range(i, len(source)):
        if source[j] == "{":
            depth += 1
        elif source[j] == "}":
            depth -= 1
            if depth == 0:
                return source[start : j + 1]
    raise AssertionError(f"unbalanced braces after {query}")


# --- reduced motion ---------------------------------------------------------


def test_reduced_motion_is_a_blanket_rule_not_a_list(css):
    """A list goes stale the moment anyone adds an animation.

    The failure is invisible to whoever adds it and visible only to the person
    who asked their system to stop moving things.
    """
    block = _media_block(css, "@media (prefers-reduced-motion: reduce)")
    assert re.search(r"\*,\s*\*::before,\s*\*::after", block), (
        "the reduced-motion block does not apply to everything, so a new animation will ship moving"
    )
    assert "animation-duration" in block
    assert "transition: none !important" in block


def test_reduced_motion_also_stops_smooth_scrolling(css):
    """Scroll-behavior is motion too, and it is the one people forget."""
    block = _media_block(css, "@media (prefers-reduced-motion: reduce)")
    assert "scroll-behavior" in block


def test_every_animation_is_covered_by_the_blanket(css):
    """There is at least one animation to cover, so the rule is not vacuous."""
    assert "@keyframes" in css


# --- more contrast ----------------------------------------------------------


def test_more_contrast_strengthens_what_was_subtle(css):
    """Someone asking for more contrast is reporting that subtlety failed.

    Borders and outlines survive where two close fills do not.
    """
    block = _media_block(css, "@media (prefers-contrast: more)")
    assert "--border" in block
    assert "outline" in block
    # Muted text is the first thing to become unreadable.
    assert "--text-muted" in block


# --- print ------------------------------------------------------------------


def test_print_drops_the_interactive_furniture(css):
    """Navigation and a theme toggle mean nothing on paper."""
    block = _media_block(css, "@media print")
    for selector in (".site-nav", ".skip-link", "button"):
        assert selector in block, f"print does not hide {selector}"


def test_print_reveals_the_table_behind_each_chart(css):
    """On paper the numbers are the artifact; hovering a cell is not available."""
    block = _media_block(css, "@media print")
    assert ".chart .visually-hidden" in block


def test_print_spells_out_link_destinations(css):
    """A printed "see here" is useless; the URL is not."""
    block = _media_block(css, "@media print")
    assert "attr(href)" in block


def test_print_avoids_breaking_figures_across_pages(css):
    block = _media_block(css, "@media print")
    assert "break-inside: avoid" in block


# --- responsive and touch ---------------------------------------------------


def test_typography_is_fluid_rather_than_stepped(css):
    """`clamp()` scales between breakpoints instead of jumping at them."""
    assert "clamp(" in css


#: Every interactive control on the site, with why its size matters. Inline
#: links inside prose are deliberately absent: WCAG 2.2 exempts a target that
#: sits in a sentence, and padding one to 44px would wreck the line spacing of
#: the paragraph around it.
_CONTROLS = {
    ".skip-link": "the first control a keyboard user reaches",
    ".brand": "the header's home link",
    ".nav-toggle": "below 900px this is the only way to reach the navigation",
    ".theme-toggle": "in the sticky header, next to the nav toggle",
    ".btn": "every call to action on the site",
    ".chip": "filter controls",
    ".field input": "form fields",
}


def test_touch_targets_reach_the_minimum(css):
    """44px is the smallest reliably hittable target on a phone.

    This test used to be `assert "44px" in css`, and it passed for months
    while most of the site failed. The string was there -- on `.field input`
    and `.chip` -- and nothing checked that it reached anything else. Measured
    in a browser at 320px, the navigation toggle came back 66x23, the theme
    toggle 67x33, and the column sort buttons 13x23, which is under WCAG 2.2's
    24x24 floor as well as this project's own bar.

    An assertion that a string appears somewhere in a file is not a test of
    the thing the string was written for.
    """
    missing = []
    for selector, why in _CONTROLS.items():
        if _rule_block(css, selector) is None:
            missing.append(f"{selector} has no rule at all ({why})")
            continue
        height = _effective_min_height(css, selector)
        if height is None:
            missing.append(f"{selector} sets no minimum height ({why})")
        elif height < MINIMUM_TARGET_PX:
            missing.append(f"{selector} is {height:g}px, under {MINIMUM_TARGET_PX:g} ({why})")
    assert not missing, "controls below the touch-target minimum: " + "; ".join(missing)


def test_a_sortable_header_is_hittable_across_the_whole_cell(css):
    """`all: unset` leaves the button as small as its label.

    A column headed "#" gave a 13px-wide target. Rather than force the button
    to 44px -- which would have pushed every header row down by half its
    height on desktop too -- the cell itself is the target: two extra pixels
    of padding, and a pseudo-element that fills it.
    """
    th = _rule_block(css, ".data-table th")
    assert th is not None and "position: relative" in th, (
        "the header cell is not a positioning context, so the hit area cannot fill it"
    )
    after = _rule_block(css, ".th-sort::after")
    assert after is not None, ".th-sort has no hit area beyond its own text"
    assert "position: absolute" in after and "inset: 0" in after


def test_wide_content_scrolls_inside_its_own_container(css):
    """A table wider than a phone must not make the page scroll sideways."""
    assert "overflow-x: auto" in css


# --- the route loading state ------------------------------------------------


def test_the_route_fallback_announces_itself(css):
    """Code splitting introduced a state that did not exist before.

    A visual-only spinner tells a screen reader nothing about why the page is
    empty.
    """
    app = Path("web/src/App.tsx").read_text(encoding="utf-8")
    assert 'role="status"' in app
    assert 'aria-live="polite"' in app
    assert "visually-hidden" in app
    assert ".route-loading" in css


def _without_comments(source: str) -> str:
    """CSS comments, removed before any rule is parsed.

    Without this a rule preceded by a comment reads as a selector containing
    the whole comment, and every lookup misses -- which is how the first
    version of this test failed on CSS that was correct.
    """
    return re.sub(r"/\*.*?\*/", "", source, flags=re.S)


def _blocks(source: str, selector: str) -> list[str]:
    """Declarations of every rule naming `selector`, in source order."""
    blocks = []
    for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", _without_comments(source)):
        names = [name.strip() for name in match.group(1).split(",")]
        if any(name == selector or name.startswith(selector + ":") for name in names):
            blocks.append(match.group(2))
    return blocks


def _rule_block(source: str, selector: str) -> str | None:
    """Every declaration for `selector`, joined. None when it has no rule."""
    blocks = _blocks(source, selector)
    return "\n".join(blocks) if blocks else None


def _effective_min_height(source: str, selector: str) -> float | None:
    """The `min-height` in force, following source order for ties.

    Reading only the first rule would pass on a value a later rule overrides,
    and reading only the last would miss a value set once and never changed.
    """
    values = []
    for block in _blocks(source, selector):
        values += re.findall(r"min-height:\s*([0-9.]+)px", block)
    return float(values[-1]) if values else None
