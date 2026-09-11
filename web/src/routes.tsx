// One route table, two renderers.
//
// The browser wants code splitting: 34 routes in a single 372 KB bundle means
// someone landing on /about downloads the offload-cliff chart, the TCO
// calculator and the KV-cache page before anything appears.
//
// The prerenderer wants the opposite. `renderToString` cannot suspend, so a
// `React.lazy` component thrown at it either crashes or renders its fallback
// into the static HTML — which is the one output that must contain real
// content, because it is what a crawler and a first-time visitor see.
//
// Keeping two hand-written route lists would solve both and then drift: a
// route added to one and not the other is a page that works in the browser and
// 404s for search engines, or renders a spinner into the HTML forever. So both
// are derived from the table below, and `tests/routes.test.ts` asserts they
// still agree.

import { lazy } from 'react'
import type { ComponentType } from 'react'
import { Route } from 'react-router-dom'

// Page components have different prop shapes -- most take none, `Planned`
// takes a `kind`. The table is heterogeneous by nature, so the prop type is
// widened once here rather than at each of the thirty call sites.
type PageProps = Record<string, unknown>
type PageComponent = ComponentType<PageProps>
// The page modules genuinely disagree about props, so the widening happens
// once at this boundary rather than thirty times at the call sites.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Importer = () => Promise<{ default: ComponentType<any> }>

export interface RouteDef {
  path: string
  importer: Importer
  /**
   * The importer's source path, as Vite's manifest keys it.
   *
   * The prerenderer cannot read a closure, so the specifier is stated as data
   * too. That is a duplication, and `tests/routes.test.ts` checks each one
   * resolves to a real file and that no page is missing from the table --
   * because a wrong module name here emits a preload for a chunk that does
   * not exist, which is a 404 on every page load.
   */
  module: string
  /** Props a route needs; `Planned` serves two paths with different kinds. */
  props?: Record<string, unknown>
}

/** Every route the site serves, in the order they are declared. */
export const ROUTES: RouteDef[] = [
  { path: '/', importer: () => import('./pages/Home'), module: 'src/pages/Home.tsx' },
  { path: '/leaderboard', importer: () => import('./pages/Leaderboard'), module: 'src/pages/Leaderboard.tsx' },
  { path: '/will-it-run', importer: () => import('./pages/WillItRun'), module: 'src/pages/WillItRun.tsx' },
  { path: '/local-vs-cloud', importer: () => import('./pages/Tco'), module: 'src/pages/Tco.tsx' },
  { path: '/frontiers', importer: () => import('./pages/Pareto'), module: 'src/pages/Pareto.tsx' },
  { path: '/offload-cliff', importer: () => import('./pages/OffloadCliff'), module: 'src/pages/OffloadCliff.tsx' },
  { path: '/kv-cache', importer: () => import('./pages/KvCache'), module: 'src/pages/KvCache.tsx' },
  { path: '/recommend', importer: () => import('./pages/Recommend'), module: 'src/pages/Recommend.tsx' },
  { path: '/matchmaker', importer: () => import('./pages/Matchmaker'), module: 'src/pages/Matchmaker.tsx' },
  { path: '/submit', importer: () => import('./pages/Submit'), module: 'src/pages/Submit.tsx' },
  { path: '/hardware', importer: () => import('./pages/HardwareExplorer'), module: 'src/pages/HardwareExplorer.tsx' },
  { path: '/hardware/:fingerprint', importer: () => import('./pages/HardwareDetail'), module: 'src/pages/HardwareDetail.tsx' },
  { path: '/runtimes', importer: () => import('./pages/RuntimeExplorer'), module: 'src/pages/RuntimeExplorer.tsx' },
  { path: '/runtimes/:name', importer: () => import('./pages/RuntimeDetail'), module: 'src/pages/RuntimeDetail.tsx' },
  { path: '/models', importer: () => import('./pages/ModelExplorer'), module: 'src/pages/ModelExplorer.tsx' },
  { path: '/models/:slug', importer: () => import('./pages/ModelDetail'), module: 'src/pages/ModelDetail.tsx' },
  { path: '/models/:modelSlug/on/:gpuSlug', importer: () => import('./pages/ModelOnHardware'), module: 'src/pages/ModelOnHardware.tsx' },
  { path: '/results', importer: () => import('./pages/ResultExplorer'), module: 'src/pages/ResultExplorer.tsx' },
  { path: '/results/:runId', importer: () => import('./pages/ResultDetail'), module: 'src/pages/ResultDetail.tsx' },
  { path: '/compare', importer: () => import('./pages/Compare'), module: 'src/pages/Compare.tsx' },
  { path: '/dataset', importer: () => import('./pages/DatasetExplorer'), module: 'src/pages/DatasetExplorer.tsx' },
  { path: '/methodology', importer: () => import('./pages/Methodology'), module: 'src/pages/Methodology.tsx' },
  { path: '/compatibility', importer: () => import('./pages/CompatibilityMatrix'), module: 'src/pages/CompatibilityMatrix.tsx' },
  { path: '/docs', importer: () => import('./pages/Docs'), module: 'src/pages/Docs.tsx' },
  { path: '/community', importer: () => import('./pages/Community'), module: 'src/pages/Community.tsx' },
  { path: '/hardware-needed', importer: () => import('./pages/HardwareNeeded'), module: 'src/pages/HardwareNeeded.tsx' },
  {
    path: '/planned/enterprise',
    importer: () => import('./pages/Planned'), module: 'src/pages/Planned.tsx',
    props: { kind: 'enterprise' },
  },
  {
    path: '/planned/certification',
    importer: () => import('./pages/Planned'), module: 'src/pages/Planned.tsx',
    props: { kind: 'certification' },
  },
  { path: '/about', importer: () => import('./pages/About'), module: 'src/pages/About.tsx' },
  { path: '*', importer: () => import('./pages/NotFound'), module: 'src/pages/NotFound.tsx' },
]

/** Routes rendered without the site's chrome, inside someone else's page. */
export const EMBED_ROUTES: RouteDef[] = [
  { path: '/embed/result/:runId', importer: () => import('./pages/EmbedResult'), module: 'src/pages/EmbedResult.tsx' },
  { path: '*', importer: () => import('./pages/NotFound'), module: 'src/pages/NotFound.tsx' },
]

/** Cache so a module imported by two routes is only fetched once. */
const resolved = new Map<Importer, PageComponent>()

/**
 * Load every route component.
 *
 * Called by the prerenderer before it renders, so `renderToString` never meets
 * a component that has not arrived. Awaiting here is what lets the same tree
 * be split in the browser and complete on the server.
 */
export async function preloadRoutes(): Promise<void> {
  const all = [...ROUTES, ...EMBED_ROUTES]
  await Promise.all(
    all.map(async ({ importer }) => {
      if (!resolved.has(importer)) {
        resolved.set(importer, (await importer()).default as PageComponent)
      }
    }),
  )
}

/** Route elements backed by already-loaded components. For prerendering. */
export function eagerRouteElements(defs: RouteDef[] = ROUTES) {
  return defs.map(({ path, importer, props }) => {
    const Component = resolved.get(importer)
    if (!Component) {
      // Loud rather than a blank page: a prerender that silently skipped a
      // route would publish an empty document at a real URL.
      throw new Error(`preloadRoutes() was not awaited before rendering ${path}`)
    }
    return <Route key={path} path={path} element={<Component {...(props ?? {})} />} />
  })
}

const lazyCache = new Map<Importer, PageComponent>()

/** Route elements backed by `React.lazy`. For the browser. */
export function lazyRouteElements(defs: RouteDef[] = ROUTES) {
  return defs.map(({ path, importer, props }) => {
    let Component = lazyCache.get(importer)
    if (!Component) {
      Component = lazy(importer) as unknown as PageComponent
      lazyCache.set(importer, Component)
    }
    return <Route key={path} path={path} element={<Component {...(props ?? {})} />} />
  })
}
