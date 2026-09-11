"""The prerendered HTML has to survive contact with the browser.

Fifty-three pages of static HTML were being built, shipped, painted and then
discarded on every visit. The entry point called `createRoot`, which replaces
whatever is in the container rather than adopting it, so the static output was
doing its job for crawlers and nothing at all for readers -- who got the
server's content for an instant, then a loading skeleton until fourteen JSON
files arrived.

Nothing caught it. Every frontend test rendered components directly; none
asked whether the server's markup and the client's first render agree. The
behavioural half of that gap is now `web/tests/hydration.test.tsx`. This file
holds the parts that are about *wiring* -- the conditions that make hydration
possible in the first place, each of which is a single line someone can undo
without any test noticing.

The diagnosis is worth recording because it was not obvious: `renderToString`
emits `<!-- -->` comment nodes between adjacent text nodes and a client render
emits none, so counting comment nodes in the live DOM says which one is on
screen. The live pages had zero.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

WEB = Path("web")
MAIN = WEB / "src" / "main.tsx"
APP = WEB / "src" / "App.tsx"
ENTRY_SERVER = WEB / "src" / "entry-server.tsx"
ROUTES = WEB / "src" / "routes.tsx"
PRERENDER = WEB / "scripts" / "prerender.mjs"
SRC = WEB / "src"


@pytest.fixture(scope="module")
def main_tsx() -> str:
    return MAIN.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def app_tsx() -> str:
    return APP.read_text(encoding="utf-8")


# --- the entry point adopts the server's DOM --------------------------------


def test_the_client_hydrates_rather_than_re_rendering(main_tsx):
    """`createRoot` on a prerendered container throws the prerender away."""
    assert "hydrateRoot" in main_tsx, (
        "main.tsx does not hydrate, so every prerendered page is discarded on load"
    )


def test_an_empty_container_still_uses_createRoot(main_tsx):
    """`vite dev` serves a bare index.html. Hydrating nothing reports a
    mismatch on every page of the dev server."""
    assert "createRoot" in main_tsx
    assert "firstElementChild" in main_tsx


def test_the_dataset_is_awaited_before_hydrating(main_tsx):
    """Otherwise the first client render is the loading skeleton, which is not
    what the server rendered, and React discards the page."""
    assert "loadDataset()" in main_tsx
    # The call site, not the import line -- `hydrateRoot` is named on line two.
    hydrate = main_tsx.index("hydrateRoot(")
    assert main_tsx.index("loadDataset()") < hydrate


def test_the_current_route_chunk_is_awaited_before_hydrating(main_tsx):
    """`React.lazy` suspends on its first render even when the chunk is
    already in memory, so an unawaited route hydrates as the fallback."""
    assert "preloadRoute(" in main_tsx
    assert main_tsx.index("preloadRoute(") < main_tsx.index("hydrateRoot(")


def test_the_404_shell_is_not_hydrated(main_tsx):
    """`404.html` is the one prerendered page whose body is not its URL.

    GitHub Pages has no server-side rewrite, so a deep link to a route that
    was never prerendered gets `404.html` — home's markup under an address
    like `/results/whatever`. Hydrating that mismatches by construction, on
    every such link.
    """
    prerender = PRERENDER.read_text(encoding="utf-8")
    client = re.search(r"FALLBACK_MARKER = '([^']+)'", main_tsx)
    server = re.search(r"FALLBACK_MARKER = '([^']+)'", prerender)
    assert client is not None, "main.tsx does not check for the fallback shell"
    assert server is not None, "the prerenderer does not mark the fallback shell"
    assert client.group(1) == server.group(1), (
        "the marker is spelled differently on the two sides, so it is never found: "
        f"{client.group(1)!r} vs {server.group(1)!r}"
    )
    # Matching spellings mean nothing if neither side uses them.
    assert 'meta[name="' in main_tsx, "main.tsx never looks the marker up in the document"
    assert "<meta name=" in prerender and "404.html" in prerender, (
        "the prerenderer never writes the marker into the fallback page"
    )


def test_only_the_current_route_is_preloaded(main_tsx):
    """`preloadRoutes` (plural) would load all thirty chunks up front and undo
    the code splitting it took a rewrite to get."""
    assert "preloadRoutes" not in main_tsx


# --- the two renderers produce the same tree --------------------------------


def test_the_suspense_boundary_is_outside_the_eager_branch(app_tsx):
    """The bug that broke every page, and the easiest one to reintroduce.

    A boundary that never suspends renders no DOM, so wrapping only the
    browser's tree looks free. Hydration compares elements, not DOM: the
    client had a `<Suspense>` where the server had the route's `<div>`, and
    React discarded the prerendered HTML on all fifty-three pages.
    """
    for name in ("AppRoutes", "EmbedRoutes"):
        body = _function_body(app_tsx, name)
        assert "<Suspense" in body, f"{name} has no Suspense boundary"
        # An `if (eager) return ...` before the boundary is exactly the shape
        # that broke: one branch with it, one without.
        early_return = re.search(r"if \(eager\)[^\n]*return", body)
        assert early_return is None, (
            f"{name} returns early on `eager`, so the server and browser trees "
            "differ in shape and hydration cannot match"
        )


def test_the_eager_flag_is_passed_not_sniffed(app_tsx):
    """`typeof window === 'undefined'` is right in both real environments and
    wrong under test: jsdom defines `window`, so the "server" render in a test
    silently took the browser branch. The hydration test agreed with itself
    while every real page failed."""
    assert "eager?: boolean" in app_tsx
    server = ENTRY_SERVER.read_text(encoding="utf-8")
    assert "<AppShell eager />" in server, (
        "the server entry does not state `eager`, so it depends on a global that differs under test"
    )


def test_lazy_elements_prefer_an_already_loaded_component():
    """Otherwise `preloadRoute` has no effect: `lazy` suspends regardless."""
    source = ROUTES.read_text(encoding="utf-8")
    assert "resolved.get(importer) ?? lazyCache.get(importer)" in source


def test_route_matching_uses_react_routers_own_matcher():
    """A hand-rolled pattern check is a second source of truth, and it drifts
    on the first parameterised route -- losing hydration on every deep page."""
    source = ROUTES.read_text(encoding="utf-8")
    assert "matchPath" in source


# --- things that differ between the prerenderer and a reader's browser ------


def test_no_number_is_formatted_without_a_locale():
    """`toLocaleString()` with no argument uses the host's locale.

    Node formats with the build machine's, the reader's browser with theirs,
    and 32768 becomes "32,768" on one side and "32.768" on the other -- a text
    mismatch that costs the hydration for every reader outside the build
    machine's locale, and nobody who builds it can reproduce it. React's own
    mismatch message lists this as a cause.
    """
    offenders = []
    for path in sorted(SRC.rglob("*.ts")) + sorted(SRC.rglob("*.tsx")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"toLocaleString\(\s*\)", line):
                offenders.append(f"{path}:{number}")
    assert not offenders, (
        "these format a number in the host locale, which differs between the "
        f"prerenderer and the reader: {offenders}. Use fmtInt/fmtNum."
    )


def test_no_render_path_reads_the_clock_or_the_random_generator():
    """Both differ between build time and load time by construction."""
    offenders = []
    for path in sorted(SRC.rglob("*.tsx")):
        source = path.read_text(encoding="utf-8")
        for number, line in enumerate(source.splitlines(), 1):
            if line.lstrip().startswith("//") or line.lstrip().startswith("*"):
                continue
            if re.search(r"\bDate\.now\(\)|\bMath\.random\(\)|new Date\(\s*\)", line):
                offenders.append(f"{path}:{number}: {line.strip()[:80]}")
    assert not offenders, (
        "these change between the prerender and the page load, so the markup "
        f"cannot match: {offenders}"
    )


def _function_body(source: str, name: str) -> str:
    """The text of `function name(...) { ... }`, brace-matched."""
    match = re.search(rf"function {name}\(", source)
    assert match is not None, f"{name} not found"
    # Skip the parameter list: these components destructure their props, so the
    # first `{` after the name opens the parameter object, not the body.
    depth, i = 1, match.end()
    while depth:
        if source[i] == "(":
            depth += 1
        elif source[i] == ")":
            depth -= 1
        i += 1
    start = source.index("{", i)
    depth = 0
    for i in range(start, len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[start : i + 1]
    raise AssertionError(f"unbalanced braces in {name}")
