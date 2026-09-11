"""The route table, the prerenderer and the pages on disk must agree.

The browser takes code-split chunks. The prerenderer cannot: `renderToString`
does not suspend, so a route still loading writes its fallback into the static
HTML -- the one copy a crawler and a first-time visitor read, and the copy that
looks fine while carrying nothing.

Both are derived from one table so they cannot diverge. These are the checks
that need the filesystem; the pure ones live in `web/tests/routes.test.ts`.
They are here rather than there because the web project has no `@types/node`,
and adding it to run three `readFileSync` calls would be the wrong trade.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

WEB = Path("web")
ROUTES_TSX = WEB / "src" / "routes.tsx"
ENTRY_SERVER = WEB / "src" / "entry-server.tsx"
APP_TSX = WEB / "src" / "App.tsx"
PRERENDER = WEB / "scripts" / "prerender.mjs"

#: Pages reached by another page rather than by a path of their own.
_UNROUTED_BY_DESIGN: set[str] = set()


def _declared_modules() -> list[str]:
    source = ROUTES_TSX.read_text(encoding="utf-8")
    return re.findall(r"module: '([^']+)'", source)


def test_every_declared_module_exists():
    """A wrong module name emits a modulepreload for a chunk that is not there.

    That is a 404 on every load of the route, and the page still works, so
    nothing surfaces it except the network tab.
    """
    missing = [m for m in _declared_modules() if not (WEB / m).is_file()]
    assert not missing, f"routes name modules that do not exist: {missing}"


def test_every_page_on_disk_is_routed():
    """A page with no route is a file nobody can reach."""
    on_disk = {f"src/pages/{p.name}" for p in (WEB / "src" / "pages").glob("*.tsx")}
    routed = set(_declared_modules())
    unrouted = sorted(on_disk - routed - _UNROUTED_BY_DESIGN)
    assert not unrouted, f"pages with no route: {unrouted}"


def test_the_prerenderer_loads_every_route_before_rendering():
    """Without this the static HTML carries a spinner.

    Worse than a crash, because it publishes and looks fine.
    """
    assert "preloadRoutes" in ENTRY_SERVER.read_text(encoding="utf-8")
    assert "await prepare()" in PRERENDER.read_text(encoding="utf-8")


def test_the_app_renders_eagerly_only_without_a_window():
    source = APP_TSX.read_text(encoding="utf-8")
    assert "typeof window === 'undefined'" in source
    assert "eagerRouteElements" in source
    assert "lazyRouteElements" in source
    assert "Suspense" in source


def test_the_build_emits_a_manifest_for_the_preload_hints():
    config = (WEB / "vite.config.ts").read_text(encoding="utf-8")
    assert "manifest: true" in config
    assert "modulepreload" in PRERENDER.read_text(encoding="utf-8")


@pytest.mark.skipif(not (WEB / "dist").is_dir(), reason="site has not been built")
def test_every_modulepreload_in_the_built_site_resolves():
    """A preload pointing at a missing chunk is a 404 on every page load."""
    dist = WEB / "dist"
    missing = []
    checked = 0
    for page in dist.rglob("index.html"):
        html = page.read_text(encoding="utf-8")
        for href in re.findall(r'rel="modulepreload" href="([^"]+)"', html):
            checked += 1
            if not (dist / href.lstrip("/")).is_file():
                missing.append((page.name, href))
    assert checked, "no modulepreload hints were emitted at all"
    assert not missing, f"preloads with no target: {missing[:3]}"


@pytest.mark.skipif(not (WEB / "dist").is_dir(), reason="site has not been built")
def test_the_static_html_carries_content_rather_than_a_loading_state():
    """The whole reason the prerenderer loads routes eagerly."""
    dist = WEB / "dist"
    for page in ("index.html", "kv-cache/index.html", "leaderboard/index.html"):
        html = (dist / page).read_text(encoding="utf-8")
        assert "Loading page" not in html, f"{page} shipped the route fallback"
        text = re.sub(r"<[^>]+>", " ", html)
        assert len(re.sub(r"\s+", " ", text)) > 1500, f"{page} looks empty"
