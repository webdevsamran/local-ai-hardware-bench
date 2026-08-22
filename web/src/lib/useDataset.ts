import { useCallback, useEffect, useState } from 'react'
import { loadDataset } from './data'
import type { Dataset } from './types'

/** React hook exposing the cached dataset with loading/error states. */
export function useDataset() {
  const [dataset, setDataset] = useState<Dataset | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(() => {
    setLoading(true)
    setError(null)
    loadDataset()
      .then(setDataset)
      .catch((e: unknown) =>
        setError(e instanceof Error ? e.message : String(e)),
      )
      .finally(() => setLoading(false))
  }, [])

  useEffect(refresh, [refresh])

  return { dataset, loading, error, retry: refresh }
}