import { useMemo } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useDataset } from '../lib/useDataset'
import { Loading, ErrorState } from '../components/States'
import DataTable, { type Column } from '../components/DataTable'
import type { HardwareEntry } from '../lib/types'

interface Row extends Record<string, unknown> {
  fingerprint: string
  cpu: string
  gpu: string
  os: string
  ram_gb: number | null
  results: number
}

export default function HardwareExplorer() {
  const { dataset, loading, error, retry } = useDataset()
  const [params, setParams] = useSearchParams()
  const q = params.get('q') ?? ''
  const vendor = params.get('vendor') ?? ''

  const rows: Row[] = useMemo(() => {
    if (!dataset) return []
    return dataset.hardware.map((h: HardwareEntry) => ({
      fingerprint: h.fingerprint,
      cpu: h.cpu ?? '—',
      gpu: h.gpu ?? '—',
      os: h.os ?? '—',
      ram_gb: h.ram_gb ?? null,
      results: h.result_ids.length,
    }))
  }, [dataset])

  const vendors = useMemo(() => {
    const set = new Set<string>()
    for (const r of rows) {
      const m = /(?:^|\s)(intel|amd|nvidia|apple|qualcomm|arm)/i.exec(
        `${r.cpu} ${r.gpu}`,
      )
      if (m?.[1]) set.add(m[1].toLowerCase())
    }
    return [...set].sort()
  }, [rows])

  const filtered = rows.filter((r) => {
    if (vendor && !`${r.cpu} ${r.gpu}`.toLowerCase().includes(vendor)) return false
    if (!q) return true
    const hay = `${r.cpu} ${r.gpu} ${r.os}`.toLowerCase()
    return hay.includes(q.toLowerCase())
  })

  const columns: Column<Row>[] = [
    {
      key: 'cpu',
      label: 'CPU',
      render: (row) => (
        <Link to={`/hardware/${row.fingerprint}`}>{row.cpu}</Link>
      ),
    },
    { key: 'gpu', label: 'GPU' },
    { key: 'os', label: 'OS' },
    { key: 'ram_gb', label: 'RAM (GB)', numeric: true },
    { key: 'results', label: 'Results', numeric: true },
  ]

  function update(key: string, value: string) {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    setParams(next, { replace: true })
  }

  return (
    <div>
      <h1 className="page-title">Hardware explorer</h1>
      <p className="page-sub">
        Hardware configurations identified by CPU/GPU/NPU class fingerprints —
        never serial numbers or personal identifiers.
      </p>

      {loading && <Loading />}
      {error && <ErrorState message={error} onRetry={retry} />}

      {dataset && (
        <>
          <div className="filter-bar">
            <label className="filter-label">
              Search
              <input
                type="search"
                value={q}
                placeholder="CPU, GPU or OS…"
                onChange={(e) => update('q', e.target.value)}
              />
            </label>
            <label className="filter-label">
              Vendor
              <select value={vendor} onChange={(e) => update('vendor', e.target.value)}>
                <option value="">All vendors</option>
                {vendors.map((v) => (
                  <option key={v} value={v}>
                    {v}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <p className="muted">
            Filters are reflected in the URL — share the link directly.
          </p>
          <DataTable
            rows={filtered}
            columns={columns}
            caption="Hardware configurations"
            emptyMessage="No hardware matches these filters."
          />
        </>
      )}
    </div>
  )
}