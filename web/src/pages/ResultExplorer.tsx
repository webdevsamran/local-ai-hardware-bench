import { useMemo } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useDataset } from '../lib/useDataset'
import { Loading, ErrorState, ContributeEmptyState } from '../components/States'
import DataTable, { type Column } from '../components/DataTable'
import type { BenchmarkResultDoc } from '../lib/types'
import { fmtDate, fmtNum } from '../lib/format'

interface Row extends Record<string, unknown> {
  run_id: string
  timestamp: string
  runtime: string
  model: string
  device: string
  throughput: number | null
  ttft: number | null
}

export default function ResultExplorer() {
  const { dataset, loading, error, retry } = useDataset()
  const [params, setParams] = useSearchParams()
  const runtime = params.get('runtime') ?? ''
  const q = params.get('q') ?? ''

  const rows: Row[] = useMemo(() => {
    if (!dataset) return []
    return dataset.results.map((r: BenchmarkResultDoc) => ({
      run_id: r.run_id,
      timestamp: r.timestamp ?? '',
      runtime: r.runtime?.name ?? '—',
      model: r.model?.name ?? '—',
      device: r.runtime?.device ?? '—',
      throughput: r.metrics?.generation_tokens_per_second ?? null,
      ttft: r.metrics?.ttft_ms ?? null,
    }))
  }, [dataset])

  const runtimeOptions = useMemo(
    () => [...new Set(rows.map((r) => r.runtime))].sort(),
    [rows],
  )

  const filtered = rows.filter((r) => {
    if (runtime && r.runtime !== runtime) return false
    if (!q) return true
    return `${r.run_id} ${r.model} ${r.runtime}`.toLowerCase().includes(q.toLowerCase())
  })

  const columns: Column<Row>[] = [
    {
      key: 'run_id',
      label: 'Run ID',
      render: (row) => <Link to={`/results/${row.run_id}`}>{row.run_id}</Link>,
    },
    { key: 'timestamp', label: 'Date', render: (row) => fmtDate(row.timestamp) },
    { key: 'runtime', label: 'Runtime' },
    { key: 'model', label: 'Model' },
    { key: 'device', label: 'Device' },
    { key: 'throughput', label: 'tok/s', numeric: true, render: (r) => fmtNum(r.throughput) },
    { key: 'ttft', label: 'TTFT (ms)', numeric: true, render: (r) => fmtNum(r.ttft) },
  ]

  return (
    <div>
      <h1 className="page-title">Results</h1>
      <p className="page-sub">
        Every published benchmark run with its full metadata. Click a run for
        the complete measurement record, reproducibility data and download
        links.
      </p>

      {loading && <Loading />}
      {error && <ErrorState message={error} onRetry={retry} />}

      {dataset &&
        (rows.length === 0 ? (
          <ContributeEmptyState subject="results" />
        ) : (
          <>
            <div className="filter-bar">
              <label className="filter-label">
                Search
                <input
                  type="search"
                  value={q}
                  placeholder="Run ID or model…"
                  onChange={(e) => {
                    const next = new URLSearchParams(params)
                    if (e.target.value) next.set('q', e.target.value)
                    else next.delete('q')
                    setParams(next, { replace: true })
                  }}
                />
              </label>
              <label className="filter-label">
                Runtime
                <select
                  value={runtime}
                  onChange={(e) => {
                    const next = new URLSearchParams(params)
                    if (e.target.value) next.set('runtime', e.target.value)
                    else next.delete('runtime')
                    setParams(next, { replace: true })
                  }}
                >
                  <option value="">All runtimes</option>
                  {runtimeOptions.map((r) => (
                    <option key={r} value={r}>
                      {r}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <DataTable
              rows={filtered}
              columns={columns}
              caption="Published benchmark results"
              emptyMessage="No results match these filters."
            />
          </>
        ))}
    </div>
  )
}