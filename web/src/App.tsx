import { Suspense } from 'react'
import { BrowserRouter, Routes, useLocation } from 'react-router-dom'
import type { ReactNode } from 'react'
import Layout from './components/Layout'
import { EMBED_ROUTES, ROUTES, eagerRouteElements, lazyRouteElements } from './routes'

/**
 * Whether route components are already loaded.
 *
 * The prerenderer awaits `preloadRoutes()` and then renders synchronously,
 * because `renderToString` cannot suspend -- a lazy route would put a spinner
 * into the static HTML, which is the one output that must carry real content.
 * The browser has no such constraint and takes the split chunks.
 *
 * It is a prop with a default rather than a bare `typeof window` check inside
 * the component. The check is still the default, because it is right in both
 * real environments -- but jsdom defines `window`, so under test the "server"
 * render silently took the browser branch. That made the hydration test agree
 * with itself while the real prerenderer and the real browser disagreed, which
 * is worse than having no test. Passing it explicitly lets a test render the
 * branch the prerenderer actually renders.
 */
const DEFAULT_EAGER = typeof window === 'undefined'

/** What a visitor sees for the moment a route chunk is in flight. */
function RouteFallback() {
  return (
    <div className="route-loading" role="status" aria-live="polite">
      <span className="visually-hidden">Loading page</span>
      <span className="route-loading-bar" aria-hidden="true" />
    </div>
  )
}

/**
 * The Suspense boundary is outside the branch, and has to stay there.
 *
 * It used to wrap only the browser's tree, which looked harmless because a
 * boundary that never suspends renders no DOM of its own. Hydration does not
 * compare DOM, it compares the element tree: the client had a `<Suspense>`
 * where the server had the route's `<div>`, so every page in the site failed
 * to hydrate and React discarded the prerendered HTML. The error named the
 * boundary directly -- `+ <Suspense fallback={<RouteFallback>}>` against
 * `- <div>` -- and it is invisible until something hydrates, which nothing
 * did until now.
 *
 * It costs the prerenderer nothing: every component is already loaded by
 * `preloadRoutes()`, so the boundary is inert on that side.
 */
export function AppRoutes({ eager = DEFAULT_EAGER }: { eager?: boolean }) {
  return (
    <Suspense fallback={<RouteFallback />}>
      <Routes>{eager ? eagerRouteElements(ROUTES) : lazyRouteElements(ROUTES)}</Routes>
    </Suspense>
  )
}

/** Routes rendered bare, with none of the site's own chrome. */
function EmbedRoutes({ eager = DEFAULT_EAGER }: { eager?: boolean }) {
  return (
    <Suspense fallback={<RouteFallback />}>
      <Routes>
        {eager ? eagerRouteElements(EMBED_ROUTES) : lazyRouteElements(EMBED_ROUTES)}
      </Routes>
    </Suspense>
  )
}

export function AppShell({
  children,
  eager = DEFAULT_EAGER,
}: {
  children?: ReactNode
  eager?: boolean
}) {
  const { pathname } = useLocation()
  // An embed lives inside someone else's page, where this site's navigation,
  // footer and theme toggle would be noise wrapped around a small card. The
  // check is on the path rather than a prop so the browser and the
  // prerenderer reach the same conclusion without being told separately.
  if (pathname.startsWith('/embed/')) {
    return <EmbedRoutes eager={eager} />
  }
  return <Layout>{children ?? <AppRoutes eager={eager} />}</Layout>
}

// Vite injects the deploy sub-path ('/' locally, '/local-ai-hardware-bench/'
// on GitHub Pages). React Router wants a basename with no trailing slash.
const BASENAME = (import.meta.env.BASE_URL || '/').replace(/[/]$/, '')

export default function App({
  children,
  eager = DEFAULT_EAGER,
}: {
  children?: ReactNode
  eager?: boolean
}) {
  return (
    // BrowserRouter, not HashRouter: to a crawler '/#/models/x' is the home
    // page, so every route shared one identity and none could rank on its own.
    // Real paths rely on the prerendered HTML from scripts/prerender.mjs and
    // the 404.html fallback for deep links on GitHub Pages.
    <BrowserRouter basename={BASENAME}>
      <AppShell eager={eager}>{children}</AppShell>
    </BrowserRouter>
  )
}
