import { Link, useParams } from 'react-router-dom'
import { useDataset } from '../lib/useDataset'
import { Loading, ErrorState } from '../components/States'
import { TrustBadge, Tag } from '../components/Badge'
import CopyCommand from '../components/CopyCommand'
import { fmtDate, fmtNum, fmtPrecise } from '../lib/format'
import { SITE_URL } from '../lib/seo'

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

  // An absolute URL, because the snippet is pasted onto someone else's
  // domain where a relative path resolves to their site rather than this one.
  // `loading="lazy"` so a card below the fold costs a reader nothing, and the
  // title is what a screen reader announces in place of the frame.
  const embedSnippet =
    `<iframe src="${SITE_URL.replace(/\/$/, '')}/embed/result/${r.run_id}" ` +
    `width="440" height="260" loading="lazy" style="border:0" ` +
    `title="AIHWBench result ${r.run_id}"></iframe>`

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

      {/* What bounds this result's trustworthiness.
          Both of these were learned by getting them wrong: a benchmark taken
          during a background scan measured 118x slow while passing every other
          check, and an energy figure computed against an unstable baseline
          swung by 84x between runs of the same workload. Neither is visible
          from the metrics alone, so the page shows them next to the metrics. */}
      {(rep.machine_contention || r.energy) && (
        <section className="card">
          <h2>What bounds these numbers</h2>

          {rep.machine_contention && (
            <>
              <h3>The machine while measuring</h3>
              {rep.machine_contention.busy === true ? (
                <p className="verdict verdict-bad" role="status">
                  {rep.machine_contention.reason}
                </p>
              ) : rep.machine_contention.busy === false ? (
                <p className="muted">
                  CPU at {fmtNum(rep.machine_contention.cpu_percent)}% before
                  the run, under the{' '}
                  {fmtNum(rep.machine_contention.threshold_percent)}% threshold
                  — the hardware was free to be measured.
                </p>
              ) : (
                <p className="muted">
                  Machine load was not measured for this run, which is not the
                  same as the machine having been quiet.
                </p>
              )}
            </>
          )}

          {r.energy && (
            <>
              <h3>Energy</h3>
              {r.energy.energy_joules_per_token == null ? (
                <p className="muted">
                  {r.energy.caveat ??
                    'Per-token energy was not resolvable for this run.'}
                </p>
              ) : (
                <>
                  <dl className="kv-list">
                    <dt>Per token</dt>
                    <dd>
                      {/* Not fmtNum: 0.0703 J rendered as "0.1" loses the
                          figure entirely. */}
                      {fmtPrecise(r.energy.energy_joules_per_token)} J
                    </dd>
                    <dt>Attributable to the workload</dt>
                    <dd>
                      {fmtNum(r.energy.incremental_power_watts)} W of{' '}
                      {fmtNum(r.energy.gross_average_power_watts)} W measured
                    </dd>
                    <dt>Idle baseline</dt>
                    <dd>
                      {fmtNum(r.energy.idle_baseline_power_watts)} W
                      {r.energy.idle_power_spread_watts != null &&
                        `, itself varying by ${fmtNum(r.energy.idle_power_spread_watts)} W`}
                    </dd>
                  </dl>
                  {r.energy.incremental_is_robust === false && (
                    <p className="notice" role="note">
                      {r.energy.caveat}
                    </p>
                  )}
                </>
              )}
            </>
          )}
        </section>
      )}

      <section className="card">
        <h2>Embed this result</h2>
        <p className="muted">
          A card for a blog post or a review. It carries the hardware, the
          runtime, the confidence interval and the comparability caveat with
          it — a benchmark number quoted without those is the false precision
          this project argues against.
        </p>
        <CopyCommand command={embedSnippet} />
        <p className="muted small">
          Add <code>?theme=light</code> or <code>?theme=dark</code> to the URL
          to match your page; without it the card follows the reader's own
          system preference.
        </p>
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