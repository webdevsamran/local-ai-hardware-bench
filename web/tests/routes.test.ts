/**
 * One route table, two renderers, and the drift that would break the site.
 *
 * The browser takes code-split chunks; the prerenderer needs every component
 * already loaded, because `renderToString` cannot suspend and would otherwise
 * write a loading fallback into the static HTML — the one copy a crawler and a
 * first-time visitor read.
 *
 * Two hand-maintained lists would have satisfied both and then diverged: a
 * route in one and not the other is a page that works when clicked and 404s
 * when shared. So both are derived from `ROUTES`.
 *
 * The checks that need the filesystem — that each module exists, that no page
 * is unrouted, that the prerenderer awaits the preload — live in
 * `tests/test_frontend_routes.py`. This project has no `@types/node`, and
 * adding it for three `readFileSync` calls would be the wrong trade.
 */

import { describe, expect, it } from 'vitest'
import { EMBED_ROUTES, ROUTES } from '../src/routes'

const ALL = [...ROUTES, ...EMBED_ROUTES]

describe('the route table', () => {
  it('gives every route a module path', () => {
    for (const route of ALL) {
      expect(route.module, `${route.path} has no module`).toBeTruthy()
      expect(route.module.startsWith('src/pages/')).toBe(true)
    }
  })

  it('has no duplicate paths', () => {
    const paths = ROUTES.map((r) => r.path)
    expect(new Set(paths).size).toBe(paths.length)
  })

  it('keeps the catch-all last', () => {
    // React Router matches in order; a wildcard earlier swallows every route
    // after it, and each one silently becomes the 404 page.
    expect(ROUTES[ROUTES.length - 1]?.path).toBe('*')
    expect(ROUTES.slice(0, -1).some((r) => r.path === '*')).toBe(false)
  })

  it('declares the props a route needs', () => {
    // Planned serves two paths and renders differently for each; a missing
    // prop would render the wrong page at a real URL.
    const planned = ROUTES.filter((r) => r.module === 'src/pages/Planned.tsx')
    expect(planned).toHaveLength(2)
    for (const route of planned) {
      expect(route.props?.kind).toBeTruthy()
    }
    expect(new Set(planned.map((r) => r.props?.kind)).size).toBe(2)
  })

  it('covers every route the embed shell needs', () => {
    expect(EMBED_ROUTES.some((r) => r.path.startsWith('/embed/'))).toBe(true)
    expect(EMBED_ROUTES[EMBED_ROUTES.length - 1]?.path).toBe('*')
  })
})
