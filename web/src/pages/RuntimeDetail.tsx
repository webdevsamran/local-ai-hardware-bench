import { Link, useParams } from 'react-router-dom'
import { useDataset } from '../lib/useDataset'
import { Loading, ErrorState } from '../components/States'
import { LineChart, type LinePoint } from '../components/Charts'
import { fmtNum } from '../lib/format'

export default function RuntimeDetail() {
  const { name } = useParams()
  const { dataset, loading, error, retry } = useDataset()

  if (loading) return <Loading />
  if (error) return <ErrorState message={error} onRetry={retry} />
  if (!dataset) return null

  const rt = dataset.runtimes.find(
    (r) => r.name.toLowerCase() === (name ?? '').toLowerCase(),
  )
  if (!rt) {
    return (
      <div>
        <p className="breadcrumb">
          <Link to="/runtimes">← Runtime explorer</Link>
        </p>
        <div className="card">
          <h1 className="page-title">Runtime not found</h1>
          <p>
            No published results exist for runtime <code>{name}</code>. See the{' '}
            <Link to="/docs">docs</Link> to benchmark it yourself.
          </p>
        </div>
      </div>
    )
  }

  const results = dataset.results.filter((r) => rt.result_ids.includes(r.run_id))
  const trend = dataset.trends[rt.name] ?? []
  const throughputSeries: LinePoint[] = trend.map((t) => ({
    label: t.timestamp ?? '',
    value: t.throughput,
  }))
  const ttftSeries: LinePoint[] = trend.map((t) => ({
    label: t.timestamp ?? '',
    value: t.ttft_ms,
  }))

  return (
    <div>
      <p className="breadcrumb">
        <Link to="/runtimes">← Runtime explorer</Link>
      </p>
      <h1 className="page-title">{rt.name}</h1>
      <p className="page-sub">
        {results.length} measured result{results.length === 1 ? '' : 's'} ·
        versions measured: {rt.versions.join(', ') || '—'}
      </p>

      {trend.length > 1 && (
        <>
          <section className="card">
            <h2>Throughput over time</h2>
            <LineChart series={[{ name: 'tok/s', points: throughputSeries }]} unit="tok/s" />
          </section>
          <section className="card">
            <h2>TTFT over time</h2>
            <LineChart series={[{ name: 'ms', points: ttftSeries }]} unit="ms" />
          </section>
        </>
      )}

      <section className="card">
        <h2>Results</h2>
        <ul>
          {results.map((r) => (
            <li key={r.run_id}>
              <Link to={`/results/${r.run_id}`}>{r.run_id}</Link>{' '}
              <span className="muted">
                — v{r.runtime?.version ?? '?'} on {(r.system?.cpu ?? '').slice(0, 40)} ·{' '}
                {fmtNum(r.metrics?.generation_tokens_per_second)} tok/s
              </span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}