import { Link, useParams } from 'react-router-dom'
import { useDataset } from '../lib/useDataset'
import { Loading, ErrorState } from '../components/States'
import { BarChart } from '../components/Charts'
import { fmtNum } from '../lib/format'

export default function HardwareDetail() {
  const { fingerprint } = useParams()
  const { dataset, loading, error, retry } = useDataset()

  if (loading) return <Loading />
  if (error) return <ErrorState message={error} onRetry={retry} />
  if (!dataset) return null

  const hw = dataset.hardware.find((h) => h.fingerprint === fingerprint)
  if (!hw) {
    return (
      <div>
        <p className="breadcrumb">
          <Link to="/hardware">← Hardware explorer</Link>
        </p>
        <div className="card">
          <h1 className="page-title">Hardware not found</h1>
          <p>
            No hardware configuration with fingerprint{' '}
            <code>{fingerprint}</code> exists in the published dataset.
          </p>
        </div>
      </div>
    )
  }

  const results = dataset.results.filter((r) => hw.result_ids.includes(r.run_id))
  const throughputData = results
    .filter((r) => r.metrics?.generation_tokens_per_second != null)
    .map((r) => ({
      label: (r.runtime?.name ?? '?') + ' ' + (r.model?.name ?? '').slice(0, 12),
      value: r.metrics!.generation_tokens_per_second!,
    }))

  return (
    <div>
      <p className="breadcrumb">
        <Link to="/hardware">← Hardware explorer</Link>
      </p>
      <h1 className="page-title">{hw.cpu ?? 'Unknown CPU'}</h1>
      <p className="page-sub">
        Fingerprint <code>{hw.fingerprint}</code> · {results.length} measured
        result{results.length === 1 ? '' : 's'}
      </p>

      <section className="card">
        <h2>Configuration</h2>
        <dl className="kv-list">
          <dt>CPU</dt>
          <dd>{hw.cpu ?? '—'}</dd>
          <dt>GPU</dt>
          <dd>{hw.gpu ?? '—'}</dd>
          <dt>NPU</dt>
          <dd>{hw.npu ?? '—'}</dd>
          <dt>OS</dt>
          <dd>{hw.os ?? '—'}</dd>
          <dt>RAM</dt>
          <dd>{fmtNum(hw.ram_gb)} GB</dd>
        </dl>
      </section>

      {throughputData.length > 0 && (
        <section className="card">
          <h2>Measured generation throughput by result</h2>
          <BarChart data={throughputData} unit="tok/s" />
        </section>
      )}

      <section className="card">
        <h2>Results on this hardware</h2>
        <ul>
          {results.map((r) => (
            <li key={r.run_id}>
              <Link to={`/results/${r.run_id}`}>{r.run_id}</Link>{' '}
              <span className="muted">
                — {r.runtime?.name} · {r.model?.name} ·{' '}
                {fmtNum(r.metrics?.generation_tokens_per_second)} tok/s ·{' '}
                {fmtDate(r.timestamp)}
              </span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}

function fmtDate(iso: string | undefined): string {
  return iso ? iso.slice(0, 10) : '—'
}