// Server entry used only at build time by scripts/prerender.mjs.
//
// The site stays fully static: this renders each route to HTML once, so the
// deployed page carries its real content and its own <head> before any
// JavaScript runs. Nothing here ships to the browser.

import { renderToString } from 'react-dom/server'
import { StaticRouter } from 'react-router-dom'
import { AppShell } from './App'
import { preloadRoutes } from './routes'

// Re-exported so the prerenderer can map each route to the chunk it needs.
export { ROUTES } from './routes'
import { seedDataset } from './lib/data'
import type { Dataset } from './lib/types'

export {
  allRoutes,
  indexableRoutes,
  metaForPath,
  SITE_URL,
  SITE_NAME,
} from './lib/seo'

/**
 * Render one route to HTML with the dataset already in place.
 *
 * The dataset is seeded rather than fetched: `useDataset` returns the cached
 * value on its first render, so the markup contains the actual table rather
 * than the loading state a crawler would otherwise index.
 */
/**
 * Load every route component before any rendering happens.
 *
 * `renderToString` cannot suspend, so a route still in flight would render its
 * fallback into the static HTML -- a spinner published at a real URL, which is
 * exactly the content a crawler would index. Awaiting here is what lets the
 * browser take split chunks while the prerenderer still completes.
 */
export async function prepare(): Promise<void> {
  await preloadRoutes()
}

export function render(url: string, dataset: Dataset): string {
  seedDataset(dataset)
  return renderToString(
    // `eager` explicitly, not inferred. The components are all loaded by
    // `prepare()`, and `renderToString` cannot suspend -- but saying so here
    // is also what lets a test render this exact tree, rather than a tree that
    // merely resembles it because jsdom happens to define `window`.
    <StaticRouter location={url}>
      <AppShell eager />
    </StaticRouter>,
  )
}
