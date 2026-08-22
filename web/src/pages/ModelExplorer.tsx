import { useMemo } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useDataset } from '../lib/useDataset'
import { Loading, ErrorState, ContributeEmptyState } from '../components/States'
import DataTable, { type Column } from '../components/DataTable'
import type { ModelEntry } from '../lib/types'
import { slugify } from '../lib/format'

interface Row extends Record<string, unknown> {
  name: string
  format: string
  quantizations: string
  results: number
}

export default function ModelExplorer() {
  const { dataset, loading, error, retry } = useDataset()
  const [params, setParams] = useSearchParams()
  const q = params.get('q') ?? ''

  const rows: Row[] = useMemo(() => {
    if (!dataset) return []
    return dataset.models.map((m: ModelEntry) => ({
      name: m.name,
      format: m.format ?? '—',
      quantizations: m.quantizations.join(', ') || '—',
      results: m.result_ids.length,
    }))
  }, [dataset])

  const filtered = rows.filter((r) =>
    r.name.toLowerCase().includes(q.toLowerCase()),
  )

  const columns: Column<Row>[] = [
    {
      key: 'name',
      label: 'Model',
      render: (row) => (
        <Link to={`/models/${slugify(row.name)}`}>{row.name}</Link>
      ),
    },
    { key: 'format', label: 'Format' },
    { key: 'quantizations', label: 'Quantizations' },
    { key: 'results', label: 'Results', numeric: true },
  ]

  return (
    <div>
      <h1 className="page-title">Model explorer</h1>
      <p className="page-sub">
        Models with published benchmark results. Checksums are recorded per
        result so runs can be reproduced bit-for-bit.
      </p>

      {loading && <Loading />}
      {error && <ErrorState message={error} onRetry={retry} />}

      {dataset &&
        (rows.length === 0 ? (
          <ContributeEmptyState subject="model results" />
        ) : (
          <>
            <div className="filter-bar">
              <label className="filter-label">
                Search
                <input
                  type="search"
                  value={q}
                  placeholder="Model name…"
                  onChange={(e) => {
                    const next = new URLSearchParams(params)
                    if (e.target.value) next.set('q', e.target.value)
                    else next.delete('q')
                    setParams(next, { replace: true })
                  }}
                />
              </label>
            </div>
            <DataTable
              rows={filtered}
              columns={columns}
              caption="Models"
              emptyMessage="No models match this search."
            />
          </>
        ))}
    </div>
  )
}