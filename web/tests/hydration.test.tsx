/**
 * The client's first render must match the prerendered HTML, exactly.
 *
 * This is the test the site did not have, and the gap it left was large. The
 * entry point called `createRoot`, which discards whatever is in the container
 * and renders from scratch — so fifty-three prerendered pages were built,
 * shipped, painted and then thrown away on every visit. The static output was
 * working for crawlers and doing nothing for readers, and every existing test
 * passed the whole time, because each one rendered components directly and
 * never asked whether the server's HTML and the client's first render agree.
 *
 * Hydration is what makes that content survive, and hydration is strict: React
 * compares its first render against the DOM and gives up on any difference.
 * Two things have to be true before it starts, and both are easy to break
 * without noticing:
 *
 *   1. the dataset is present, or the first render is a loading skeleton;
 *   2. the route's own chunk has arrived, or `React.lazy` suspends and the
 *      first render is the route fallback.
 *
 * So these tests render through the real server entry, put its output in a
 * container, and hydrate it the way the browser does. A mismatch fails here
 * rather than becoming a console error nobody reads.
 */

import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { StrictMode, act } from 'react'
import { hydrateRoot } from 'react-dom/client'
import { renderToString } from 'react-dom/server'
import { StaticRouter } from 'react-router-dom'
import App, { AppShell } from '../src/App'
import { preloadRoute, preloadRoutes } from '../src/routes'
import { seedDataset } from '../src/lib/data'
import type { Dataset } from '../src/lib/types'
import { dataset as fixture } from './fixtures/dataset'

/** Routes worth checking: one plain page, one data-heavy page, one embed. */
const ROUTES_UNDER_TEST = ['/', '/kv-cache', '/about', '/embed/result/test-run-1']

/**
 * Hydration failures arrive through `onRecoverableError`, not `console.error`.
 *
 * That distinction matters: an earlier version of this file watched the
 * console, and when the mismatch was reintroduced to check the test could
 * fail, three of the four route cases still passed. React reports a recovered
 * hydration mismatch to the root's own callback and to `window.onerror`; the
 * console is where it ends up by default, not where it is raised.
 */
let recovered: unknown[] = []
let errors: unknown[][] = []
let originalError: typeof console.error

beforeEach(() => {
  recovered = []
  errors = []
  originalError = console.error
  console.error = (...args: unknown[]) => {
    errors.push(args)
  }
})

afterEach(() => {
  console.error = originalError
  vi.restoreAllMocks()
})

/**
 * The prerenderer's own output for a route.
 *
 * `eager` is passed explicitly, exactly as `entry-server.tsx` passes it. This
 * is the whole reason the test is worth anything: the flag defaults to
 * `typeof window === 'undefined'`, and jsdom defines `window`, so without the
 * prop this function would render the *browser's* tree and then compare it to
 * itself. It would have passed while every real page failed to hydrate --
 * which is what happened.
 */
function serverHtml(path: string): string {
  seedDataset(fixture as unknown as Dataset)
  return renderToString(
    <StaticRouter location={path}>
      <AppShell eager />
    </StaticRouter>,
  )
}

/** Comment nodes, which is how server HTML is told from a client re-render. */
function countComments(root: Node): number {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_COMMENT)
  let n = 0
  while (walker.nextNode()) n++
  return n
}

async function hydrateAt(path: string) {
  await preloadRoutes()
  const container = document.createElement('div')
  container.innerHTML = serverHtml(path)
  document.body.appendChild(container)
  // Counted before hydration, because hydration is what might destroy them.
  const staging = document.createElement('div')
  staging.innerHTML = container.innerHTML

  window.history.replaceState(null, '', path)
  let root: ReturnType<typeof hydrateRoot> | null = null
  // Exactly what `main.tsx` mounts: the real `App` (which supplies
  // BrowserRouter and the deploy basename) inside StrictMode. Hydrating
  // `AppShell` on its own would test a tree the browser never renders.
  await act(async () => {
    root = hydrateRoot(
      container,
      <StrictMode>
        <App />
      </StrictMode>,
      { onRecoverableError: (error) => recovered.push(error) },
    )
  })
  return { container, root, serverComments: countComments(staging) }
}

describe('hydration', () => {
  for (const path of ROUTES_UNDER_TEST) {
    it(`matches the prerendered HTML at ${path}`, async () => {
      const { container, serverComments } = await hydrateAt(path)

      const reported = [
        ...recovered.map((e) => (e instanceof Error ? e.message : String(e))),
        ...errors.flatMap((args) =>
          args.filter(
            (a): a is string =>
              typeof a === 'string' &&
              /hydrat|did not match|server rendered|server HTML/i.test(a),
          ),
        ),
      ]
      expect(reported.map((m) => m.slice(0, 500)), `hydration mismatch at ${path}`).toEqual([])

      // React recovers from a mismatch by re-rendering, so silence is not
      // proof on its own: check the server's own nodes are still here.
      if (serverComments > 0) {
        expect(countComments(container), `server HTML replaced at ${path}`).toBe(serverComments)
      }

      // Not enough that React stayed quiet: the content has to still be
      // there. The embed card is deliberately small, so the floor is the
      // point at which a page is obviously more than a spinner.
      const floor = path.startsWith('/embed/') ? 120 : 400
      expect(container.textContent?.length ?? 0).toBeGreaterThan(floor)
    })
  }

  it('keeps the server nodes rather than replacing them', async () => {
    // The signature of the original bug. `renderToString` emits `<!-- -->`
    // between adjacent text nodes; a client render from scratch emits none. If
    // those comment nodes survive, the DOM in the browser is the DOM the
    // server sent.
    const path = '/kv-cache'
    const staging = document.createElement('div')
    staging.innerHTML = serverHtml(path)
    const before = countComments(staging)
    expect(
      before,
      'the server HTML has no text-boundary comments, so this test cannot tell hydration from replacement',
    ).toBeGreaterThan(0)

    const { container } = await hydrateAt(path)
    expect(countComments(container), 'the server HTML was discarded and re-rendered').toBe(before)
  })
})

describe('preloadRoute', () => {
  it('resolves the chunk the current path needs', async () => {
    // Without this the route renders through `React.lazy`, which suspends on
    // its first render even when the chunk is already in memory -- so the
    // first client render is the route fallback and hydration cannot match.
    await expect(preloadRoute('/kv-cache')).resolves.toBeUndefined()
  })

  it('resolves a parameterised path', async () => {
    // `/results/:runId` must match, or every deep page loses its hydration.
    await expect(preloadRoute('/results/test-run-1')).resolves.toBeUndefined()
  })

  it('does not throw on a path no route serves', async () => {
    await expect(preloadRoute('/no-such-page-anywhere')).resolves.toBeUndefined()
  })
})
