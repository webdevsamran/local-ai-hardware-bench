import { Link, useParams } from 'react-router-dom'
import { useDataset } from '../lib/useDataset'
import { Loading, ErrorState } from '../components/States'
import { BarChart } from '../components/Charts'
import { fmtNum, slugify } from '../lib/format'

export default function ModelDetail() {
  const { slug } = useParams()
  const { dataset, loading, error, retry } = useDataset()

  if (loading) return <Loading />
  if (error) return <ErrorState message={error} onRetry={retry} />
  if (!dataset) return null

  const model = dataset.models.find((m) => slugify(m.name) === slug)
  if (!model) {
    return (
      <div>
        <p className="breadcrumb">
          <Link to="/models">← Model explorer</Link>
        </p>
        <div className="card">
          <h1 className="page-title">Model not found</h1>
          <p>
            No published results exist for model <code>{slug}</code>.
          </p>
        </div>
      </div>
    )
  }

  const results = dataset.results.filter((r) =>
    model.result_ids.includes(r.run_id),
  )
  const throughputData = results
    .filter((r) => r.metrics?.generation_tokens_per_second != null)
    .map((r) => ({
      label: r.runtime?.name ?? '?',
      value: r.metrics!.generation_tokens_per_second!,
    }))
  const ttftData = results
    .filter((r) => r.metrics?.ttft_ms != null)
    .map((r) => ({
      label: r.runtime?.name ?? '?',
      value: r.metrics!.ttft_ms!,
    }))

  return (
    <div>
      <p className="breadcrumb">
        <Link to="/models">← Model explorer</Link>
      </p>
      <h1 className="page-title">{model.name}</h1>
      <p className="page-sub">
        Format: {model.format ?? '—'} · Quantizations:{' '}
        {model.quantizations.join(', ') || '—'}
      </p>

      {throughputData.length > 0 && (
        <section className="card">
          <h2>Generation throughput by runtime</h2>
          <BarChart data={throughputData} unit="tok/s" />
        </section>
      )}
      {ttftData.length > 0 && (
        <section className="card">
          <h2>Time to first token by runtime</h2>
          <BarChart data={ttftData} unit="ms" />
        </section>
      )}

      <section className="card">
        <h2>Results</h2>
        <ul>
          {results.map((r) => (
            <li key={r.run_id}>
              <Link to={`/results/${r.run_id}`}>{r.run_id}</Link>{' '}
              <span className="muted">
                — {r.runtime?.name} on {(r.system?.gpu ?? r.system?.cpu ?? '').slice(0, 40)} ·{' '}
                {fmtNum(r.metrics?.generation_tokens_per_second)} tok/s
              </span>
            </li>
          ))}
        </ul>
      </section>

      {model.checksums.length > 0 && (
        <section className="card">
          <h2>Recorded checksums</h2>
          <ul>
            {model.checksums.map((c) => (
              <li key={c}>
                <code>{c}</code>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}