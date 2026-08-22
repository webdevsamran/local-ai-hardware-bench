import { Link } from 'react-router-dom'
import { useDataset } from '../lib/useDataset'
import { Loading, ErrorState, ContributeEmptyState } from '../components/States'

export default function RuntimeExplorer() {
  const { dataset, loading, error, retry } = useDataset()

  return (
    <div>
      <h1 className="page-title">Runtime explorer</h1>
      <p className="page-sub">
        Inference runtimes with published benchmark results. Versions listed
        are exactly the ones that were measured.
      </p>

      {loading && <Loading />}
      {error && <ErrorState message={error} onRetry={retry} />}

      {dataset &&
        (dataset.runtimes.length === 0 ? (
          <ContributeEmptyState subject="runtime results" />
        ) : (
          <div className="grid cols-3">
            {dataset.runtimes.map((rt) => (
              <div key={rt.name} className="card">
                <h2>
                  <Link to={`/runtimes/${encodeURIComponent(rt.name)}`}>
                    {rt.name}
                  </Link>
                </h2>
                <p className="muted">
                  {rt.result_ids.length} result
                  {rt.result_ids.length === 1 ? '' : 's'} · versions:{' '}
                  {rt.versions.join(', ') || '—'}
                </p>
                <p>
                  Devices: {rt.device_options.join(', ') || '—'}
                </p>
              </div>
            ))}
          </div>
        ))}
    </div>
  )
}