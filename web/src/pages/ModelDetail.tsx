import { Link, useParams } from 'react-router-dom'
import { useDataset } from '../lib/useDataset'
import { Loading, ErrorState } from '../components/States'
import { BarChart } from '../components/Charts'
import { fmtNum, slugify } from '../lib/format'

/**
 * How much weight a licence claim carries. A licence read out of the artifact
 * can be checked by anyone holding it; one a maintainer typed cannot, and
 * saying so is the difference between a record and an assurance.
 */
function licenceBasis(source?: string | null): string {
  if (source === 'gguf-header') return "read from the file's own GGUF header"
  if (source === 'ollama-api') return 'reported by Ollama from the publisher'
  if (source === 'declared') return 'declared by a maintainer, not read from the artifact'
  return 'source unstated'
}

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

      <section className="card">
        <h2>Licence and provenance</h2>
        {model.zoo ? (
          <>
            <dl className="zoo-facts">
              <dt>Licence</dt>
              <dd>
                {model.zoo.license ? (
                  <>
                    {model.zoo.license_link ? (
                      <a href={model.zoo.license_link} rel="noreferrer noopener" target="_blank">
                        {model.zoo.license}
                      </a>
                    ) : (
                      model.zoo.license
                    )}
                    <span className="muted"> — {licenceBasis(model.zoo.license_source)}</span>
                  </>
                ) : (
                  <span className="muted">not recorded</span>
                )}
              </dd>
              {model.zoo.obtain && (
                <>
                  <dt>Obtain</dt>
                  <dd>
                    <code>{model.zoo.obtain}</code>
                  </dd>
                </>
              )}
              <dt>Verify</dt>
              <dd>
                <code>aihwbench zoo verify {model.zoo.key}</code>
              </dd>
            </dl>
            <p className="muted note">
              {model.zoo.resolved_by === 'checksum'
                ? 'Matched to this model by checksum, so the results above measured these exact weights.'
                : 'Matched by name only: the results above recorded no checksum, so nothing confirms they measured this exact file.'}{' '}
              This is not legal advice — read the licence before relying on it.
            </p>
          </>
        ) : (
          <p className="muted">
            No zoo entry covers this model, so its licence and origin are unknown. Unknown is not
            permission: check the terms yourself before using it.
          </p>
        )}
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
          {model.zoo?.checksum_kind && (
            <p className="muted note">
              {model.zoo.checksum_kind === 'weights-sha256'
                ? 'A hash of the weights file, so it is comparable across runtimes.'
                : 'A hash of a served configuration, not of the weights alone.'}{' '}
              Results from different runtimes can record different kinds of hash for the same
              weights; the zoo is what ties them together.
            </p>
          )}
        </section>
      )}
    </div>
  )
}