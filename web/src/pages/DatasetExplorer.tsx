import { useDataset } from '../lib/useDataset'
import { Loading, ErrorState } from '../components/States'
import { fmtInt } from '../lib/format'

export default function DatasetExplorer() {
  const { dataset, loading, error, retry } = useDataset()

  return (
    <div>
      <h1 className="page-title">Dataset explorer</h1>
      <p className="page-sub">
        The canonical dataset backing this site, generated deterministically
        from <code>results/published/</code>. Every file is versioned and
        hash-manifested in the repository.
      </p>

      {loading && <Loading />}
      {error && <ErrorState message={error} onRetry={retry} />}

      {dataset && (
        <>
          <section className="grid cols-4">
            <div className="card stat">
              <div className="value">{fmtInt(dataset.index.results_count)}</div>
              <p className="muted">Results</p>
            </div>
            <div className="card stat">
              <div className="value">{fmtInt(dataset.index.hardware_count)}</div>
              <p className="muted">Hardware configs</p>
            </div>
            <div className="card stat">
              <div className="value">{fmtInt(dataset.index.runtime_count)}</div>
              <p className="muted">Runtimes</p>
            </div>
            <div className="card stat">
              <div className="value">{fmtInt(dataset.index.model_count)}</div>
              <p className="muted">Models</p>
            </div>
          </section>

          <section className="card">
            <h2>Generated data files</h2>
            <p>
              These static JSON files are what this site consumes — the same
              files CI regenerates and verifies for freshness:
            </p>
            <ul>
              {['index', 'results', 'hardware', 'runtimes', 'models', 'leaderboard', 'trends'].map(
                (name) => (
                  <li key={name}>
                    <a href={`data/${name}.json`} download>
                      data/{name}.json
                    </a>
                  </li>
                ),
              )}
            </ul>
          </section>

          <section className="card">
            <h2>Dataset governance</h2>
            <ul>
              <li>
                Results are never silently deleted — corrections use
                invalidation records with reasons and replacement references.
              </li>
              <li>
                Each result carries a trust state: unreviewed, verified,
                flagged, invalidated or superseded.
              </li>
              <li>
                Snapshot manifests record SHA-256 hashes of every member file
                so history is auditable.
              </li>
              <li>
                Regenerate locally with{' '}
                <code>python scripts/generate_frontend_data.py</code>.
              </li>
            </ul>
          </section>
        </>
      )}
    </div>
  )
}