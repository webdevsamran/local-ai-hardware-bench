import { useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useDataset } from '../lib/useDataset'
import { Loading, ErrorState, ContributeEmptyState } from '../components/States'
import DataTable, { type Column } from '../components/DataTable'
import FilterBar, { type FilterSpec } from '../components/FilterBar'
import type { LeaderboardRow } from '../lib/types'
import { fmtNum } from '../lib/format'

// Facets are declared once and derived from the data, so a filter can never
// offer a value that matches nothing.
const FILTERS: FilterSpec<LeaderboardRow>[] = [
  { key: 'runtime', label: 'Runtime', valueOf: (r) => r.runtime },
  { key: 'model', label: 'Model', valueOf: (r) => r.model },
  { key: 'gpu', label: 'GPU', valueOf: (r) => r.gpu },
  { key: 'vram', label: 'VRAM', valueOf: (r) => r.vram_tier },
  { key: 'quant', label: 'Quantization', valueOf: (r) => r.quantization },
  { key: 'device', label: 'Device', valueOf: (r) => r.device },
  { key: 'trust', label: 'Trust state', valueOf: (r) => r.trust },
]

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
    unit: 'per watt',
    note: 'Higher is better. Only shown when power telemetry was available. tok/s/W and inf/s/W are different quantities and are never ranked against each other.',
  },
}

interface Group {
  id: number
  label: string
  rows: LeaderboardRow[]
}

/** Group the rows of one view by their comparison group, preserving order. */
function groupRows(rows: LeaderboardRow[]): Group[] {
  const byId = new Map<number, Group>()
  for (const row of rows) {
    let group = byId.get(row.group)
    if (!group) {
      group = { id: row.group, label: row.group_label, rows: [] }
      byId.set(row.group, group)
    }
    group.rows.push(row)
  }
  return Array.from(byId.values())
}

export default function Leaderboard() {
  const { dataset, loading, error, retry } = useDataset()
  const [view, setView] = useState<View>('throughput')
  const [params, setParams] = useSearchParams()

  const allRows = dataset?.leaderboard[view] ?? []

  // Filters live in the URL so a filtered view is shareable and survives a
  // reload -- the same reason the compare page keeps its selection there.
  const selected = useMemo(() => {
    const out: Record<string, string> = {}
    for (const spec of FILTERS) {
      const value = params.get(spec.key)
      if (value) out[spec.key] = value
    }
    return out
  }, [params])

  const rows = useMemo(
    () =>
      allRows.filter((row) =>
        FILTERS.every((spec) => {
          const wanted = selected[spec.key]
          return !wanted || spec.valueOf(row) === wanted
        }),
      ),
    [allRows, selected],
  )

  function setFilter(key: string, value: string) {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    setParams(next, { replace: true })
  }

  function clearFilters() {
    const next = new URLSearchParams(params)
    for (const spec of FILTERS) next.delete(spec.key)
    setParams(next, { replace: true })
  }

  const groups = useMemo(() => groupRows(rows), [rows])
  const rankable = groups.filter((g) => g.rows.length > 1)

  const columns: Column<LeaderboardRow>[] = [
    { key: 'rank', label: '#', numeric: true },
    {
      key: 'run_id',
      label: 'Result',
      render: (row) => <Link to={`/results/${row.run_id}`}>{row.run_id}</Link>,
    },
    { key: 'cpu', label: 'CPU' },
    { key: 'gpu', label: 'GPU' },
    {
      key: 'value',
      label: VIEWS[view].unit,
      numeric: true,
      render: (row) =>
        row.unit ? `${fmtNum(row.value)} ${row.unit}` : fmtNum(row.value),
    },
  ]

  return (
    <div>
      <h1 className="page-title">Leaderboard</h1>
      <p className="page-sub">
        Ranked exclusively by measured results submitted to the repository. No
        opaque composite score is used, and{' '}
        <strong>ranking is only ever within a comparison group</strong> — a set
        of results the comparison-safety classifier says may honestly be
        compared with one another.
      </p>

      {loading && <Loading />}
      {error && <ErrorState message={error} onRetry={retry} />}

      {dataset && (
        <>
          <div
            className="filter-bar"
            role="tablist"
            aria-label="Leaderboard metric"
          >
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

          <FilterBar
            rows={allRows}
            specs={FILTERS}
            selected={selected}
            onChange={setFilter}
            onReset={clearFilters}
          />

          {rows.length === 0 && allRows.length > 0 ? (
            <p className="notice" role="status">
              No result matches these filters.{' '}
              <button type="button" className="link-button" onClick={clearFilters}>
                Clear them
              </button>{' '}
              to see all {allRows.length}.
            </p>
          ) : rows.length === 0 ? (
            <ContributeEmptyState subject="leaderboard entries" />
          ) : (
            <>
              {rankable.length === 0 ? (
                <p className="notice" role="note">
                  <strong>Nothing is comparable yet.</strong> These{' '}
                  {rows.length} result{rows.length === 1 ? '' : 's'} fall into{' '}
                  {groups.length} group{groups.length === 1 ? '' : 's'} of one,
                  so each is a single measurement rather than a ranking. A
                  second result for the same model and runtime on different
                  hardware is what makes a group rankable — see{' '}
                  <Link to="/hardware-needed">hardware needed</Link>.
                </p>
              ) : (
                <p className="notice" role="note">
                  {groups.length} comparison group
                  {groups.length === 1 ? '' : 's'}, of which {rankable.length}{' '}
                  contain{rankable.length === 1 ? 's' : ''} more than one result
                  and can be ranked.
                </p>
              )}

              {groups.map((group) => (
                <section key={group.id} className="leaderboard-group">
                  <h2 className="group-title">{group.label}</h2>
                  {group.rows.length === 1 && (
                    <p className="muted small">
                      Single result — nothing to compare it against yet.
                    </p>
                  )}
                  <DataTable
                    rows={group.rows}
                    columns={columns}
                    caption={`${VIEWS[view].label} for ${group.label}`}
                    emptyMessage="No measured results for this view yet."
                  />
                </section>
              ))}
            </>
          )}
        </>
      )}
    </div>
  )
}
