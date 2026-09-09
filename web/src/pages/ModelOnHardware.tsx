import { useMemo } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useDataset } from '../lib/useDataset'
import { Loading, ErrorState } from '../components/States'
import DataTable, { type Column } from '../components/DataTable'
import { fmtNum, slugify } from '../lib/format'
import type { BenchmarkResultDoc } from '../lib/types'

// One page per model-on-GPU pair.
//
// "How fast is <model> on a <card>" is the query people actually type, and it
// is a different question from "how fast is this model" or "how fast is this
// card". Answering it on its own URL is the difference between ranking for it
// and being a row inside a page about something else.

export default function ModelOnHardware() {
  const { modelSlug, gpuSlug } = useParams()
  const { dataset, loading, error, retry } = useDataset()

  const matches = useMemo(() => {
    if (!dataset) return []
    return dataset.results.filter(
      (r) =>
        slugify(r.model?.name ?? '') === modelSlug &&
        slugify(r.system?.gpu ?? '') === gpuSlug,
    )
  }, [dataset, modelSlug, gpuSlug])

  const columns: Column<BenchmarkResultDoc>[] = [
    {
      key: 'run_id',
      label: 'Result',
      render: (row) => <Link to={`/results/${row.run_id}`}>{row.run_id}</Link>,
    },
    { key: 'run_id', label: 'Runtime', render: (row) => row.runtime?.name ?? '—' },
    {
      key: 'run_id',
      label: 'tok/s',
      numeric: true,
      render: (row) => fmtNum(row.metrics?.generation_tokens_per_second),
    },
    {
      key: 'run_id',
      label: 'TTFT ms',
      numeric: true,
      render: (row) => fmtNum(row.metrics?.ttft_ms),
    },
    {
      key: 'run_id',
      label: 'Peak VRAM MB',
      numeric: true,
      render: (row) => fmtNum(row.metrics?.peak_vram_mb),
    },
  ]

  const modelName = matches[0]?.model?.name ?? modelSlug
  const gpuName = matches[0]?.system?.gpu ?? gpuSlug

  return (
    <div>
      {loading && <Loading />}
      {error && <ErrorState message={error} onRetry={retry} />}

      {dataset && (
        <>
          <p className="muted small">
            <Link to="/models">Models</Link> ·{' '}
            <Link to={`/models/${modelSlug}`}>{modelName}</Link>
          </p>
          <h1 className="page-title">
            {modelName} on {gpuName}
          </h1>

          {matches.length === 0 ? (
            <p className="notice" role="note">
              No published result measures this model on this GPU.{' '}
              <Link to="/docs">Running the benchmark</Link> on that combination
              is what would put a number here.
            </p>
          ) : (
            <>
              <p className="page-sub">
                {matches.length} measured result
                {matches.length === 1 ? '' : 's'}, with the full environment of
                each recorded. Results from different runtimes are listed
                together but are <strong>not</strong> ranked against one
                another — see the{' '}
                <Link to="/compare">comparison-safety classifier</Link> for why.
              </p>
              <DataTable
                rows={matches}
                columns={columns}
                caption={`Measured results for ${modelName} on ${gpuName}`}
                emptyMessage="No measured results."
              />
              <h2 className="section-title">Environment</h2>
              <ul className="measured-list">
                <li>CPU: {matches[0]?.system?.cpu ?? '—'}</li>
                <li>GPU: {gpuName}</li>
                <li>
                  VRAM:{' '}
                  {matches[0]?.system?.gpu_vram_mb
                    ? `${fmtNum(matches[0].system.gpu_vram_mb)} MB`
                    : '—'}
                </li>
                <li>OS: {matches[0]?.system?.os ?? '—'}</li>
              </ul>
            </>
          )}
        </>
      )}
    </div>
  )
}
