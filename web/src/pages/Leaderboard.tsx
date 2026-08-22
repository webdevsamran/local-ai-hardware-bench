import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useDataset } from '../lib/useDataset'
import { Loading, ErrorState, ContributeEmptyState } from '../components/States'
import DataTable, { type Column } from '../components/DataTable'
import type { LeaderboardRow } from '../lib/types'
import { fmtNum } from '../lib/format'

type View = 'throughput' | 'ttft' | 'perf_watt'

const VIEWS: Record<View, { label: string; unit: string; note: string }> = {
  throughput: {
    label: 'Generation throughput',
    unit: 'tok/s',
    note: 'Higher is better. Measured generation tokens per second.',
  },
  ttft: {
    label: 'Time to first token',
    unit: 'ms',
    note: 'Lower is better. Measured TTFT in milliseconds.',
  },
  perf_watt: {
    label: 'Performance per watt',
    unit: 'tok/s/W',
    note: 'Higher is better. Only shown when power telemetry was available.',
  },
}

export default function Leaderboard() {
  const { dataset, loading, error, retry } = useDataset()
  const [view, setView] = useState<View>('throughput')

  const columns: Column<LeaderboardRow>[] = [
    { key: 'rank', label: '#', numeric: true },
    {
      key: 'run_id',
      label: 'Result',
      render: (row) => <Link to={`/results/${row.run_id}`}>{row.run_id}</Link>,
    },
    { key: 'runtime', label: 'Runtime' },
    { key: 'model', label: 'Model' },
    { key: 'cpu', label: 'CPU' },
    { key: 'gpu', label: 'GPU' },
    {
      key: 'value',
      label: VIEWS[view].unit,
      numeric: true,
      render: (row) => fmtNum(row.value),
    },
  ]

  return (
    <div>
      <h1 className="page-title">Global leaderboard</h1>
      <p className="page-sub">
        Ranked exclusively by measured results submitted to the repository.
        Ranks are per-metric; no opaque composite score is used.
      </p>

      {loading && <Loading />}
      {error && <ErrorState message={error} onRetry={retry} />}

      {dataset && (
        <>
          <div className="filter-bar" role="tablist" aria-label="Leaderboard metric">
            {(Object.keys(VIEWS) as View[]).map((v) => (
              <button
                key={v}
                role="tab"
                aria-selected={view === v}
                className={`btn ${view === v ? 'primary' : 'secondary'}`}
                onClick={() => setView(v)}
              >
                {VIEWS[v].label}
              </button>
            ))}
          </div>
          <p className="muted">{VIEWS[view].note}</p>
          {dataset.leaderboard[view].length === 0 ? (
            <ContributeEmptyState subject="leaderboard entries" />
          ) : (
            <DataTable
              rows={dataset.leaderboard[view]}
              columns={columns}
              caption={`Leaderboard ranked by ${VIEWS[view].label}`}
              emptyMessage="No measured results for this view yet."
            />
          )}
        </>
      )}
    </div>
  )
}