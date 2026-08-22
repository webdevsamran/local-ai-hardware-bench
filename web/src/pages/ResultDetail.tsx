import { Link, useParams } from 'react-router-dom'
import { useDataset } from '../lib/useDataset'
import { Loading, ErrorState } from '../components/States'
import { TrustBadge, Tag } from '../components/Badge'
import CopyCommand from '../components/CopyCommand'
import { fmtDate, fmtNum } from '../lib/format'

export default function ResultDetail() {
  const { runId } = useParams()
  const { dataset, loading, error, retry } = useDataset()

  if (loading) return <Loading />
  if (error) return <ErrorState message={error} onRetry={retry} />
  if (!dataset) return null

  const r = dataset.results.find((x) => x.run_id === runId)
  if (!r) {
    return (
      <div>
        <p className="breadcrumb">
          <Link to="/results">← Results</Link>
        </p>
        <div className="card">
          <h1 className="page-title">Result not found</h1>
          <p>No published result with run ID <code>{runId}</code>.</p>
        </div>
      </div>
    )
  }

  const m = r.metrics ?? {}
  const rep = r.reproducibility ?? {}
  const sys = r.system ?? {}

  function downloadJson() {
    const blob = new Blob([JSON.stringify(r, null, 2)], {
      type: 'application/json',
    })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${r!.run_id}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div>
      <p className="breadcrumb">
        <Link to="/results">← Results</Link>
      </p>
      <h1 className="page-title">{r.run_id}</h1>
      <p className="page-sub">
        {fmtDate(r.timestamp)} · schema v{r.schema_version} ·{' '}
        <TrustBadge />{' '}
        <Tag>{r.runtime?.name ?? 'unknown runtime'}</Tag>{' '}
        <Tag>{r.runtime?.device ?? 'device ?'}</Tag>
      </p>

      <section className="grid cols-4" aria-label="Key metrics">
        <div className="card stat">
          <div className="value">{fmtNum(m.generation_tokens_per_second)}</div>
          <p className="muted">Generation tok/s</p>
        </div>
        <div className="card stat">
          <div className="value">{fmtNum(m.ttft_ms)}</div>
          <p className="muted">TTFT (ms)</p>
        </div>
        <div className="card stat">
          <div className="value">{fmtNum(m.p95_latency_ms)}</div>
          <p className="muted">P95 latency (ms)</p>
        </div>
        <div className="card stat">
          <div className="value">{fmtNum(m.performance_per_watt)}</div>
          <p className="muted">tok/s per watt</p>
        </div>
      </section>

      <section className="card">
        <h2>Full metrics</h2>
        <dl className="kv-list">
          {Object.entries({
            'Load time (ms)': m.load_time_ms,
            'Prompt tok/s': m.prompt_tokens_per_second,
            'Total latency (ms)': m.total_latency_ms,
            'P50 latency (ms)': m.p50_latency_ms,
            'Peak RAM (MB)': m.peak_ram_mb,
            'Peak VRAM (MB)': m.peak_vram_mb,
            'Avg CPU util (%)': m.avg_cpu_util_percent,
            'Avg GPU util (%)': m.avg_gpu_util_percent,
            'Max temperature (C)': m.max_temperature_c,
            'Average power (W)': m.average_power_watts,
          }).map(([k, v]) => (
            <div key={k} style={{ display: 'contents' }}>
              <dt>{k}</dt>
              <dd>{fmtNum(v as number | null | undefined)}</dd>
            </div>
          ))}
        </dl>
        <p className="muted">
          Values shown as “—” were not measurable on this run and are recorded
          as null in the dataset.
        </p>
      </section>

      <section className="card">
        <h2>Environment</h2>
        <dl className="kv-list">
          <dt>OS</dt>
          <dd>{sys.os ?? '—'} {sys.os_version ?? ''}</dd>
          <dt>CPU</dt>
          <dd>{sys.cpu ?? '—'} ({fmtNum(sys.cpu_cores_physical)} cores / {fmtNum(sys.cpu_cores_logical)} threads)</dd>
          <dt>GPU</dt>
          <dd>{sys.gpu ?? '—'}{sys.gpu_vram_mb ? ` (${fmtNum(sys.gpu_vram_mb)} MB VRAM)` : ''}</dd>
          <dt>RAM</dt>
          <dd>{fmtNum(sys.ram_gb)} GB</dd>
          <dt>Runtime</dt>
          <dd>{r.runtime?.name} {r.runtime?.version ?? ''}</dd>
          <dt>Model</dt>
          <dd>{r.model?.name ?? '—'}</dd>
          <dt>Checksum</dt>
          <dd><code>{r.model?.checksum ?? '—'}</code></dd>
        </dl>
      </section>

      <section className="card">
        <h2>Reproducibility</h2>
        <dl className="kv-list">
          <dt>Prompt</dt>
          <dd>{rep.prompt ?? '—'}</dd>
          <dt>Max tokens</dt>
          <dd>{rep.max_tokens ?? '—'}</dd>
          <dt>Temperature / seed</dt>
          <dd>{rep.temperature ?? '—'} / {rep.seed ?? '—'}</dd>
          <dt>Context length</dt>
          <dd>{rep.context_length ?? '—'}</dd>
          <dt>Warmup / iterations</dt>
          <dd>{rep.warmup_runs ?? '—'} / {rep.iterations ?? '—'}</dd>
          <dt>Python</dt>
          <dd>{rep.python_version ?? '—'}</dd>
        </dl>
        {rep.command && (
          <>
            <h3>Exact command</h3>
            <CopyCommand command={rep.command} />
          </>
        )}
      </section>

      <section className="card">
        <h2>Download</h2>
        <button type="button" className="btn secondary" onClick={downloadJson}>
          Download result JSON
        </button>
        <p className="muted">
          The file is the verbatim published document, suitable for{' '}
          <code>aihwbench validate</code>, comparison and bundle creation.
        </p>
      </section>
    </div>
  )
}