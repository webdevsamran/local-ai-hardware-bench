import { useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useDataset } from '../lib/useDataset'
import { Loading, ErrorState } from '../components/States'
import { fmtNum } from '../lib/format'

const METRICS: { key: string; label: string; lowerBetter?: boolean; unit: string }[] = [
  { key: 'generation_tokens_per_second', label: 'Generation throughput', unit: 'tok/s' },
  { key: 'prompt_tokens_per_second', label: 'Prompt processing', unit: 'tok/s' },
  { key: 'ttft_ms', label: 'TTFT', unit: 'ms', lowerBetter: true },
  { key: 'total_latency_ms', label: 'Total latency', unit: 'ms', lowerBetter: true },
  { key: 'p95_latency_ms', label: 'P95 latency', unit: 'ms', lowerBetter: true },
  { key: 'peak_vram_mb', label: 'Peak VRAM', unit: 'MB', lowerBetter: true },
  { key: 'peak_ram_mb', label: 'Peak RAM', unit: 'MB', lowerBetter: true },
  { key: 'average_power_watts', label: 'Average power', unit: 'W', lowerBetter: true },
  { key: 'performance_per_watt', label: 'Perf per watt', unit: 'tok/s/W' },
]

export default function Compare() {
  const { dataset, loading, error, retry } = useDataset()
  const [params, setParams] = useSearchParams()
  const aId = params.get('a') ?? ''
  const bId = params.get('b') ?? ''

  const options = useMemo(
    () => (dataset ? dataset.results.map((r) => r.run_id).sort() : []),
    [dataset],
  )
  const a = dataset?.results.find((r) => r.run_id === aId)
  const b = dataset?.results.find((r) => r.run_id === bId)

  function update(key: string, value: string) {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    setParams(next, { replace: true })
  }

  return (
    <div>
      <h1 className="page-title">Compare results</h1>
      <p className="page-sub">
        Side-by-side comparison of two published runs. Metrics that were not
        measured in either run are shown as “—” for that side.
      </p>

      {loading && <Loading />}
      {error && <ErrorState message={error} onRetry={retry} />}

      {dataset && (
        <>
          <div className="filter-bar">
            <label className="filter-label">
              Result A
              <select value={aId} onChange={(e) => update('a', e.target.value)}>
                <option value="">Select…</option>
                {options.map((id) => (
                  <option key={id} value={id}>{id}</option>
                ))}
              </select>
            </label>
            <label className="filter-label">
              Result B
              <select value={bId} onChange={(e) => update('b', e.target.value)}>
                <option value="">Select…</option>
                {options.map((id) => (
                  <option key={id} value={id}>{id}</option>
                ))}
              </select>
            </label>
          </div>

          {a && b && (
            <section className="card">
              <h2>
                {a.run_id} vs {b.run_id}
              </h2>
              <p className="muted">
                A: {a.runtime?.name} · {a.model?.name} — B:{' '}
                {b.runtime?.name} · {b.model?.name}
              </p>
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th scope="col">Metric</th>
                      <th scope="col" className="numeric">A</th>
                      <th scope="col" className="numeric">B</th>
                      <th scope="col" className="numeric">Δ (B vs A)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {METRICS.map((metric) => {
                      const av = a.metrics?.[
                        metric.key as keyof NonNullable<typeof a.metrics>
                      ] as number | null | undefined
                      const bv = b.metrics?.[
                        metric.key as keyof NonNullable<typeof b.metrics>
                      ] as number | null | undefined
                      const delta =
                        av != null && bv != null && av !== 0
                          ? ((bv - av) / Math.abs(av)) * 100
                          : null
                      return (
                        <tr key={metric.key}>
                          <td>{metric.label} ({metric.unit})</td>
                          <td className="numeric">{fmtNum(av)}</td>
                          <td className="numeric">{fmtNum(bv)}</td>
                          <td className="numeric">{delta == null ? '—' : `${delta > 0 ? '+' : ''}${delta.toFixed(1)}%`}</td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
              <p className="muted">
                Comparisons are only meaningful between similar workloads;
                check the workload parameters on each result page before
                drawing conclusions.
              </p>
            </section>
          )}
          {!a || !b ? (
            <p className="muted">Select two results above to compare.</p>
          ) : null}
        </>
      )}
    </div>
  )
}