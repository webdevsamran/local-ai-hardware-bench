"""A heatmap cell's number has to stay readable at every tint, in both themes.

Colour is the second channel here, never the only one: every cell carries its
value as text. That only holds if the text is legible against the tint behind
it, and the tint that works in one theme does not work in the other.

Measured in a real browser before this test existed. At a 70% maximum mix the
darkest cell gave **5.0:1** against the text in light mode and **3.4:1** in
dark, which fails the 4.5:1 WCAG AA needs for normal text. The accent sits
brighter relative to a dark surface, so the same mix costs more contrast there.

There was a second bug under it. The dark cap was written after the light
default in the stylesheet, and `:root` and `[data-theme='dark']` have equal
specificity -- so the later rule won and the override did nothing. Source order
decided an accessibility outcome, which is why the ordering is asserted here
too rather than left to whoever edits the file next.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

STYLES = Path("web/src/styles.css")

#: WCAG 2.2 AA for normal-sized text.
AA_NORMAL_TEXT = 4.5


def _hex_to_rgb(value: str) -> tuple[float, float, float]:
    value = value.strip().lstrip("#")
    if len(value) == 3:
        value = "".join(c * 2 for c in value)
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _relative_luminance(rgb: tuple[float, float, float]) -> float:
    def channel(v: float) -> float:
        v /= 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    la, lb = _relative_luminance(a), _relative_luminance(b)
    high, low = max(la, lb), min(la, lb)
    return (high + 0.05) / (low + 0.05)


def _blend(
    fg: tuple[float, float, float], bg: tuple[float, float, float], alpha: float
) -> tuple[float, float, float]:
    """Composite a semi-transparent tint over an opaque surface."""
    return tuple(fg[i] * alpha + bg[i] * (1 - alpha) for i in range(3))  # type: ignore[return-value]


def _tokens(block: str) -> dict[str, str]:
    return dict(re.findall(r"--([a-z0-9-]+):\s*([^;]+);", block))


def _theme_block(source: str, selector: str) -> dict[str, str]:
    start = source.index(selector)
    end = source.index("}", start)
    return _tokens(source[start:end])


@pytest.fixture(scope="module")
def css() -> str:
    return STYLES.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "theme,selector", [("light", ":root {"), ("dark", "[data-theme='dark'] {")]
)
def test_the_darkest_heatmap_cell_stays_readable(css, theme, selector):
    """At full intensity, which is the worst case by construction."""
    light = _theme_block(css, ":root {")
    tokens = {**light, **_theme_block(css, selector)}

    accent = _hex_to_rgb(tokens["accent"])
    surface = _hex_to_rgb(tokens["surface"])
    text = _hex_to_rgb(tokens["text"])
    cap = float(tokens["heat-max"].strip().rstrip("%")) / 100.0

    blended = _blend(accent, surface, cap)
    ratio = _contrast(text, blended)
    assert ratio >= AA_NORMAL_TEXT, (
        f"{theme}: the darkest cell gives {ratio:.2f}:1 against its text, "
        f"under the {AA_NORMAL_TEXT}:1 AA threshold. Lower --heat-max for this theme."
    )


def test_each_theme_sets_its_own_cap(css):
    """One cap cannot serve both.

    The accent is brighter against a dark surface, so a mix tuned for light
    mode eats more of the contrast there.
    """
    assert "heat-max" in _theme_block(css, ":root {")
    assert "heat-max" in _theme_block(css, "[data-theme='dark'] {")


def test_the_light_default_is_declared_before_the_dark_override(css):
    """Equal specificity, so source order decides.

    Written the other way round, the dark cap was overridden by the light
    default and the theme silently kept a failing tint.
    """
    root_cap = css.index("--heat-max", css.index(":root {"))
    dark_selector = css.index("[data-theme='dark'] {")
    assert root_cap < dark_selector, (
        "the :root --heat-max is declared after [data-theme='dark'], so it "
        "overrides the dark cap and dark mode reverts to the light tint"
    )


def test_the_value_is_in_the_cell_so_colour_is_never_the_only_channel():
    """A tint a reader cannot distinguish must not be carrying the meaning."""
    component = Path("web/src/components/Distributions.tsx").read_text(encoding="utf-8")
    # The measured value is rendered as text inside every shaded cell.
    assert "{value.toFixed(value < 10 ? 2 : 0)}" in component
    assert 'className="heat-cell numeric"' in component


def test_more_contrast_replaces_the_tint_with_an_outline(css):
    """Someone asking for more contrast is saying the subtle version failed.

    An outline does not depend on telling two close fills apart.
    """
    start = css.index("@media (prefers-contrast: more)")
    block = css[start : css.index("\n}\n", start)]
    assert "heat-cell" in block
    assert "outline" in block
