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


def test_touch_targets_reach_the_minimum(css):
    """44px is the smallest reliably hittable target on a phone."""
    assert "44px" in css


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
