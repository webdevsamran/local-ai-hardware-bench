// Server entry used only at build time by scripts/prerender.mjs.
//
// The site stays fully static: this renders each route to HTML once, so the
// deployed page carries its real content and its own <head> before any
// JavaScript runs. Nothing here ships to the browser.

import { renderToString } from 'react-dom/server'
import { StaticRouter } from 'react-router-dom'
import { AppShell } from './App'
import { seedDataset } from './lib/data'
import type { Dataset } from './lib/types'

export { allRoutes, metaForPath, SITE_URL, SITE_NAME } from './lib/seo'

/**
 * Render one route to HTML with the dataset already in place.
 *
 * The dataset is seeded rather than fetched: `useDataset` returns the cached
 * value on its first render, so the markup contains the actual table rather
 * than the loading state a crawler would otherwise index.
 */
export function render(url: string, dataset: Dataset): string {
  seedDataset(dataset)
  return renderToString(
    <StaticRouter location={url}>
      <AppShell />
    </StaticRouter>,
  )
}
