import { useCallback, useEffect, useState } from 'react'
import { loadDataset, peekDataset } from './data'
import type { Dataset } from './types'

/**
 * React hook exposing the cached dataset with loading/error states.
 *
 * When the dataset is already cached -- seeded by the prerenderer, or fetched
 * earlier in this session -- the first render returns it rather than a loading
 * state, and no fetch is issued. That is what lets the static HTML carry real
 * content instead of a spinner, which is the difference between a page search
 * engines can index and one they cannot.
 */
export function useDataset() {
  const seeded = peekDataset()
  const [dataset, setDataset] = useState<Dataset | null>(seeded)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(seeded === null)

  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    loadDataset()
      .then(setDataset)
      .catch((e: unknown) =>
        setError(e instanceof Error ? e.message : String(e)),
      )
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    // Already seeded or cached: rendering it is the whole job.
    if (peekDataset()) return
    load()
  }, [load])

  return { dataset, loading, error, retry: load }
}
