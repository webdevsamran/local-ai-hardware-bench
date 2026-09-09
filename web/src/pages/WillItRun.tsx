import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useDataset } from '../lib/useDataset'
import { Loading, ErrorState } from '../components/States'
import { estimateModelFit, offloadFraction } from '../lib/fit'
import { fmtNum } from '../lib/format'

// "Will this model run on my machine?" is the first question every local-AI
// newcomer asks. This answers it from an explicit estimate, and — where the
// dataset has one — shows the measured result next to it, which is the part
// no calculator can offer.

const PRESET_VRAM = [
  { label: 'No discrete GPU', mb: 0 },
  { label: '6 GB', mb: 6144 },
  { label: '8 GB', mb: 8192 },
  { label: '12 GB', mb: 12288 },
  { label: '16 GB', mb: 16384 },
  { label: '24 GB', mb: 24576 },
]

const PRESET_PARAMS = ['0.5B', '1B', '3B', '7B', '8B', '13B', '32B', '70B']

interface Verdict {
  tone: 'ok' | 'warn' | 'bad' | 'unknown'
  headline: string
  detail: string
}

function verdictFor(
  totalGb: number | null,
  spill: number | null,
  reason: string,
): Verdict {
  if (totalGb === null) {
    return {
      tone: 'unknown',
      headline: 'Not enough information to estimate',
      detail: reason,
    }
  }
  if (spill === null) {
    return {
      tone: 'unknown',
      headline: `About ${totalGb.toFixed(1)} GB needed`,
      detail: 'Enter your VRAM to see whether it fits on the GPU.',
    }
  }
  if (spill === 0) {
    return {
      tone: 'ok',
      headline: 'Fits entirely in VRAM',
      detail: `An estimated ${totalGb.toFixed(1)} GB of weights and overhead fits in your GPU memory, so nothing has to spill to system RAM.`,
    }
  }
  if (spill <= 0.35) {
    return {
      tone: 'warn',
      headline: `Runs, but about ${Math.round(spill * 100)}% spills to system RAM`,
      detail:
        'Partial offload works, and it is much slower than staying resident. Throughput falls sharply once layers leave the GPU — this is the single biggest performance cliff in local inference.',
    }
  }
  return {
    tone: 'bad',
    headline: `About ${Math.round(spill * 100)}% would run on the CPU`,
    detail:
      'Expect a large slowdown. A smaller model, or a more aggressive quantization, will usually be far faster than offloading this much.',
  }
}

export default function WillItRun() {
  const { dataset, loading, error, retry } = useDataset()
  const [vramMb, setVramMb] = useState<number>(8192)
  const [ramGb, setRamGb] = useState<number>(16)
  const [params, setParams] = useState<string>('7B')
  const [quantization, setQuantization] = useState<string>('q4_k_m')

  const quantOptions = useMemo(
    () => Object.keys(dataset?.constants.bits_per_weight ?? {}).sort(),
    [dataset],
  )

  const estimate = useMemo(() => {
    if (!dataset) return null
    return estimateModelFit(
      dataset.constants,
      params,
      quantization,
      vramMb > 0 ? vramMb : null,
      ramGb * 1000,
    )
  }, [dataset, params, quantization, vramMb, ramGb])

  const spill = estimate
    ? offloadFraction(estimate.estimated_total_gb, vramMb > 0 ? vramMb : null)
    : null

  // Measured runs for this quantization, which beat any estimate.
  const measured = useMemo(() => {
    if (!dataset) return []
    return dataset.results.filter(
      (r) =>
        (r.model?.quantization ?? '').toLowerCase() === quantization.toLowerCase(),
    )
  }, [dataset, quantization])

  return (
    <div>
      <h1 className="page-title">Will this run on my PC?</h1>
      <p className="page-sub">
        Enter your hardware and the model you are considering. The answer is an{' '}
        <strong>estimate</strong> from parameter count and quantization — the
        same arithmetic <code>aihwbench fit</code> uses — not a measurement. Where
        the dataset has a real result for your configuration, it is shown
        alongside, and it always wins.
      </p>

      {loading && <Loading />}
      {error && <ErrorState message={error} onRetry={retry} />}

      {dataset && estimate && (
        <>
          <div className="wizard-grid">
            <label className="field">
              <span className="field-label">GPU memory (VRAM)</span>
              <select
                value={vramMb}
                onChange={(e) => setVramMb(Number(e.target.value))}
              >
                {PRESET_VRAM.map((v) => (
                  <option key={v.mb} value={v.mb}>
                    {v.label}
                  </option>
                ))}
              </select>
            </label>

            <label className="field">
              <span className="field-label">System RAM (GB)</span>
              <input
                type="number"
                min={2}
                max={512}
                step={2}
                value={ramGb}
                onChange={(e) => setRamGb(Number(e.target.value))}
              />
            </label>

            <label className="field">
              <span className="field-label">Model size</span>
              <select value={params} onChange={(e) => setParams(e.target.value)}>
                {PRESET_PARAMS.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
            </label>

            <label className="field">
              <span className="field-label">Quantization</span>
              <select
                value={quantization}
                onChange={(e) => setQuantization(e.target.value)}
              >
                {quantOptions.map((q) => (
                  <option key={q} value={q}>
                    {q}
                  </option>
                ))}
              </select>
            </label>
          </div>

          {(() => {
            const v = verdictFor(
              estimate.estimated_total_gb,
              spill,
              estimate.reason,
            )
            return (
              <div className={`verdict verdict-${v.tone}`} role="status">
                <h2 className="verdict-headline">{v.headline}</h2>
                <p className="verdict-detail">{v.detail}</p>
                {estimate.estimated_total_gb !== null && (
                  <dl className="verdict-figures">
                    <div>
                      <dt>Weights</dt>
                      <dd>{fmtNum(estimate.estimated_weights_gb)} GB</dd>
                    </div>
                    <div>
                      <dt>With overhead</dt>
                      <dd>{fmtNum(estimate.estimated_total_gb)} GB</dd>
                    </div>
                    <div>
                      <dt>Outside VRAM</dt>
                      <dd>{spill === null ? '—' : `${Math.round(spill * 100)}%`}</dd>
                    </div>
                  </dl>
                )}
              </div>
            )
          })()}

          <p className="muted small">
            {dataset.constants.note}. Overhead factor{' '}
            {dataset.constants.overhead_factor}× covers KV cache, activations and
            runtime allocation; the KV cache grows with context length, so a long
            context needs more than this shows.
          </p>

          <h2 className="section-title">Measured results at this quantization</h2>
          {measured.length === 0 ? (
            <p className="notice" role="note">
              No published result uses <code>{quantization}</code> yet, so there is
              nothing measured to check this estimate against.{' '}
              <Link to="/docs">Running the benchmark</Link> on your own machine is
              what turns this estimate into data.
            </p>
          ) : (
            <ul className="measured-list">
              {measured.map((r) => (
                <li key={r.run_id}>
                  <Link to={`/results/${r.run_id}`}>{r.run_id}</Link> —{' '}
                  {r.model?.name} on {r.runtime?.name},{' '}
                  {r.system?.gpu ?? r.system?.cpu}
                  {r.metrics?.generation_tokens_per_second != null && (
                    <>
                      {' '}
                      · <strong>{fmtNum(r.metrics.generation_tokens_per_second)}</strong>{' '}
                      tok/s
                    </>
                  )}
                  {r.metrics?.peak_vram_mb != null && (
                    <> · {fmtNum(r.metrics.peak_vram_mb)} MB peak VRAM measured</>
                  )}
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  )
}
