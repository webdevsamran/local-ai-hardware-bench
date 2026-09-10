// Data loading from the generated static dataset (web/public/data/*.json).
// The production site is fully static; no backend is required.

import type { Dataset } from './types'
import { assertDataset } from './validate'

export interface LoadState<T> {
  data: T | null
  loading: boolean
  error: string | null
}

let cache: Dataset | null = null
let inflight: Promise<Dataset> | null = null

async function fetchDataset(): Promise<Dataset> {
  const [
    index,
    results,
    hardware,
    runtimes,
    models,
    leaderboard,
    trends,
    constants,
    comparability,
    pareto,
    recommend,
    privacy,
    cliff,
  ] =
    await Promise.all(
      [
        'index',
        'results',
        'hardware',
        'runtimes',
        'models',
        'leaderboard',
        'trends',
        'constants',
        'comparability',
        'pareto',
        'recommend',
        'privacy',
        'cliff',
      ].map(
        async (name) => {
          // Absolute (base-anchored), not relative. Under BrowserRouter the
          // page URL can be /models/foo, where a relative `data/x.json`
          // resolves to /models/data/x.json and 404s. BASE_URL carries the
          // GitHub Pages sub-path and always ends in a slash.
          const r = await fetch(`${import.meta.env.BASE_URL}data/${name}.json`)
          if (!r.ok)
            throw new Error(`Failed to load data/${name}.json (${r.status})`)
          return r.json()
        },
      ),
    )
  const dataset = {
    index,
    results,
    hardware,
    runtimes,
    models,
    leaderboard,
    trends,
    constants,
    comparability,
    pareto,
    recommend,
    privacy,
    cliff,
  }
  // Fail closed: corruption or schema drift must surface here, not as
  // silently undefined fields in the UI.
  assertDataset(dataset)
  return dataset
}

/** Loads the full dataset once and caches it for the session. */
export function loadDataset(): Promise<Dataset> {
  if (cache) return Promise.resolve(cache)
  if (!inflight) {
    inflight = fetchDataset().then((d) => {
      cache = d
      return d
    })
  }
  return inflight
}

/**
 * Supply the dataset synchronously.
 *
 * The browser fetches `data/*.json`, but the prerenderer reads those files
 * from disk and seeds them here before rendering, so static HTML contains the
 * real content rather than a loading spinner. A page whose content only
 * appears after client-side fetch is a page search engines index as empty.
 */
export function seedDataset(dataset: Dataset): void {
  cache = dataset
}

/** The cached dataset, or null when it has not been loaded or seeded yet. */
export function peekDataset(): Dataset | null {
  return cache
}

export function resultById(dataset: Dataset, runId: string | undefined) {
  if (!runId) return undefined
  return dataset.results.find((r) => r.run_id === runId)
}