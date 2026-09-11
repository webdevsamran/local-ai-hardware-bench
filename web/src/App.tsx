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
 */
function useEager(): boolean {
  return typeof window === 'undefined'
}

/** What a visitor sees for the moment a route chunk is in flight. */
function RouteFallback() {
  return (
    <div className="route-loading" role="status" aria-live="polite">
      <span className="visually-hidden">Loading page</span>
      <span className="route-loading-bar" aria-hidden="true" />
    </div>
  )
}

export function AppRoutes() {
  if (useEager()) {
    return <Routes>{eagerRouteElements(ROUTES)}</Routes>
  }
  return (
    <Suspense fallback={<RouteFallback />}>
      <Routes>{lazyRouteElements(ROUTES)}</Routes>
    </Suspense>
  )
}

/** Routes rendered bare, with none of the site's own chrome. */
function EmbedRoutes() {
  if (useEager()) {
    return <Routes>{eagerRouteElements(EMBED_ROUTES)}</Routes>
  }
  return (
    <Suspense fallback={<RouteFallback />}>
      <Routes>{lazyRouteElements(EMBED_ROUTES)}</Routes>
    </Suspense>
  )
}

export function AppShell({ children }: { children?: ReactNode }) {
  const { pathname } = useLocation()
  // An embed lives inside someone else's page, where this site's navigation,
  // footer and theme toggle would be noise wrapped around a small card. The
  // check is on the path rather than a prop so the browser and the
  // prerenderer reach the same conclusion without being told separately.
  if (pathname.startsWith('/embed/')) {
    return <EmbedRoutes />
  }
  return <Layout>{children ?? <AppRoutes />}</Layout>
}

// Vite injects the deploy sub-path ('/' locally, '/local-ai-hardware-bench/'
// on GitHub Pages). React Router wants a basename with no trailing slash.
const BASENAME = (import.meta.env.BASE_URL || '/').replace(/[/]$/, '')

export default function App({ children }: { children?: ReactNode }) {
  return (
    // BrowserRouter, not HashRouter: to a crawler '/#/models/x' is the home
    // page, so every route shared one identity and none could rank on its own.
    // Real paths rely on the prerendered HTML from scripts/prerender.mjs and
    // the 404.html fallback for deep links on GitHub Pages.
    <BrowserRouter basename={BASENAME}>
      <AppShell>{children}</AppShell>
    </BrowserRouter>
  )
}
