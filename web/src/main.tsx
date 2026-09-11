import { StrictMode } from 'react'
import { createRoot, hydrateRoot } from 'react-dom/client'
import App from './App'
import { loadDataset } from './lib/data'
import { preloadRoute } from './routes'
import './styles.css'

// Hydrate the prerendered HTML rather than replacing it.
//
// This file used to call `createRoot` unconditionally, which discards whatever
// is already in the container and renders from scratch. The effect was that
// fifty-three prerendered pages of real content were built, shipped, painted,
// and then thrown away on every single visit: React wiped the server HTML, the
// dataset had not been fetched yet, and the page fell back to a loading
// skeleton until fourteen JSON files arrived. The static output was doing
// nothing for real visitors, only for crawlers -- which is the hardest kind of
// defect to notice, because every test passed and every page looked right by
// the time anyone looked at it.
//
// What gave it away: `renderToString` emits `<!-- -->` comment nodes between
// adjacent text nodes, and the live DOM had none of them. Server HTML, client
// nodes.
//
// Hydration is stricter than rendering. React compares its first client render
// against the existing DOM, so both things the server had must be present
// before we start:
//
//   1. the dataset, or the first render is the loading skeleton;
//   2. the current route's chunk, or `React.lazy` suspends and the first
//      render is the route fallback.
//
// Both are awaited here. The cost is that interactivity waits for the dataset
// fetch -- but the page is fully readable throughout, because the prerendered
// content now stays on screen instead of being replaced by a skeleton for the
// same interval. Links are real `<a href>` elements in that HTML, so they work
// before React attaches.

const container = document.getElementById('root')!
const tree = (
  <StrictMode>
    <App />
  </StrictMode>
)

/**
 * The one prerendered document whose markup does not describe its own URL.
 *
 * GitHub Pages has no server-side rewrite, so a deep link to a route that was
 * never prerendered is served `404.html` — whose body is the home page while
 * the address bar says `/results/whatever`. It is prerendered, and it is the
 * one page the client must not adopt: hydrating home's markup against a
 * different route's render mismatches by construction. The prerenderer stamps
 * this marker on that file and nothing else.
 */
const FALLBACK_MARKER = 'aihwbench-fallback'

/**
 * Whether this document arrived with content that belongs to this URL.
 *
 * False under `vite dev`, which serves the bare index.html with an empty root
 * — there is nothing to hydrate there, and hydrating an empty container would
 * report a mismatch on every page of the dev server.
 */
const prerendered =
  container.firstElementChild !== null &&
  document.querySelector(`meta[name="${FALLBACK_MARKER}"]`) === null

async function start(): Promise<void> {
  if (!prerendered) {
    createRoot(container).render(tree)
    return
  }
  try {
    await Promise.all([loadDataset(), preloadRoute(window.location.pathname)])
  } catch {
    // The dataset failed, or a chunk did. The tree we would hydrate is an
    // error state and the DOM holds real content, so they cannot match. Render
    // over it instead of hydrating: a visible error beats a mismatch React
    // recovers from by doing this anyway, with a console error attached.
    createRoot(container).render(tree)
    return
  }
  hydrateRoot(container, tree)
}

void start()
