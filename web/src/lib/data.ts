// Data loading from the generated static dataset (web/public/data/*.json).
// The production site is fully static; no backend is required.

import type { Dataset } from './types'

export interface LoadState<T> {
  data: T | null
  loading: boolean
  error: string | null
}

let cache: Dataset | null = null
let inflight: Promise<Dataset> | null = null

async function fetchDataset(): Promise<Dataset> {
  const [index, results, hardware, runtimes, models, leaderboard, trends] =
    await Promise.all(
      ['index', 'results', 'hardware', 'runtimes', 'models', 'leaderboard', 'trends'].map(
        async (name) => {
          const r = await fetch(`data/${name}.json`)
          if (!r.ok)
            throw new Error(`Failed to load data/${name}.json (${r.status})`)
          return r.json()
        },
      ),
    )
  return { index, results, hardware, runtimes, models, leaderboard, trends }
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

export function resultById(dataset: Dataset, runId: string | undefined) {
  if (!runId) return undefined
  return dataset.results.find((r) => r.run_id === runId)
}