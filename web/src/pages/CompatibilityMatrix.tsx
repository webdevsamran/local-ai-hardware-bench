import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import { useDataset } from '../lib/useDataset'
import { Loading, ErrorState } from '../components/States'

/**
 * Compatibility matrix: which runtime × device combinations actually have
 * measured results. Cells are derived from published data only — an empty
 * cell means "not measured yet", never "unsupported".
 */
export default function CompatibilityMatrix() {
  const { dataset, loading, error, retry } = useDataset()

  const { runtimes, devices, cells } = useMemo(() => {
    const runtimes = new Set<string>()
    const devices = new Set<string>()
    const cells = new Map<string, number>()
    if (dataset) {
      for (const r of dataset.results) {
        const rt = r.runtime?.name
        const dev = r.runtime?.device
        if (!rt || !dev) continue
        runtimes.add(rt)
        devices.add(dev)
        const key = `${rt}|${dev}`
        cells.set(key, (cells.get(key) ?? 0) + 1)
      }
    }
    return {
      runtimes: [...runtimes].sort(),
      devices: [...devices].sort(),
      cells,
    }
  }, [dataset])

  return (
    <div>
      <h1 className="page-title">Compatibility matrix</h1>
      <p className="page-sub">
        Runtime × device combinations with at least one measured result. A
        blank cell means <em>no measurement published yet</em> — it does not
        imply incompatibility.
      </p>

      {loading && <Loading />}
      {error && <ErrorState message={error} onRetry={retry} />}

      {dataset && (
        <div className="table-wrap">
          <table className="data-table matrix-table">
            <caption className="visually-hidden">
              Measured runtime and device combinations
            </caption>
            <thead>
              <tr>
                <th scope="col">Runtime</th>
                {devices.map((d) => (
                  <th scope="col" key={d}>{d}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {runtimes.map((rt) => (
                <tr key={rt}>
                  <th scope="row">
                    <Link to={`/runtimes/${encodeURIComponent(rt)}`}>{rt}</Link>
                  </th>
                  {devices.map((d) => {
                    const n = cells.get(`${rt}|${d}`) ?? 0
                    return (
                      <td key={d} className={n > 0 ? 'yes' : 'no'}>
                        {n > 0 ? `✓ ${n}` : '—'}
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}