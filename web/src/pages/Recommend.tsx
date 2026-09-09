import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useDataset } from '../lib/useDataset'
import { Loading, ErrorState } from '../components/States'
import { recommendConfiguration } from '../lib/recommend'
import { fmtNum } from '../lib/format'

// "What should I actually run on this machine?"
//
// A calculator can size a model against memory. What makes this a
// recommendation rather than arithmetic is that the runtime and device are
// anchored on results people measured, and the page says which parts are
// which — an estimated ceiling and a measured runtime are not the same kind
// of claim, and presenting them identically would be the same error the
// comparison-safety classifier exists to prevent.

const PRESET_VRAM = [
  { label: 'No discrete GPU', mb: 0 },
  { label: '6 GB', mb: 6144 },
  { label: '8 GB', mb: 8192 },
  { label: '12 GB', mb: 12288 },
  { label: '16 GB', mb: 16384 },
  { label: '24 GB', mb: 24576 },
]

export default function Recommend() {
  const { dataset, loading, error, retry } = useDataset()
  const [vramMb, setVramMb] = useState(8192)
  const [ramGb, setRamGb] = useState(32)

  const recommendation = useMemo(() => {
    if (!dataset) return null
    return recommendConfiguration(
      dataset.constants,
      vramMb > 0 ? vramMb : null,
      ramGb,
      dataset.results,
    )
  }, [dataset, vramMb, ramGb])

  return (
    <div>
      <h1 className="page-title">What should I run on this machine?</h1>
      <p className="page-sub">
        A model size, a runtime, a device and a context length for the hardware
        you describe. The size is an <strong>estimate</strong> from your memory
        budget; the runtime is anchored on results people actually measured,
        and the page says which is which.
      </p>

      {loading && <Loading />}
      {error && <ErrorState message={error} onRetry={retry} />}

      {dataset && recommendation && (
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
          </div>

          <div
            className={`verdict verdict-${
              recommendation.evidence_tier === 'measured' ? 'ok' : 'warn'
            }`}
            role="status"
          >
            <h2 className="verdict-headline">
              {recommendation.recommended_model_parameters_b === null
                ? 'Not enough information'
                : `Up to about ${recommendation.recommended_model_parameters_b}B parameters at ${recommendation.assumed_quantization}`}
            </h2>
            <p className="verdict-detail">{recommendation.uncertainty}</p>
            <dl className="verdict-figures">
              <div>
                <dt>Runtime</dt>
                <dd>{recommendation.recommended_runtime ?? '—'}</dd>
              </div>
              <div>
                <dt>Device</dt>
                <dd>{recommendation.recommended_device}</dd>
              </div>
              <div>
                <dt>Context</dt>
                <dd>{recommendation.recommended_context_length} tokens</dd>
              </div>
              <div>
                <dt>Evidence</dt>
                <dd>{recommendation.evidence_tier}</dd>
              </div>
            </dl>
          </div>

          <h2 className="section-title">How this was reached</h2>
          <ul className="measured-list">
            {recommendation.reasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>

          <h2 className="section-title">Checked against the fit estimator</h2>
          <p className="muted">
            {recommendation.fit_check.fits === true ? (
              <>
                The recommended size needs an estimated{' '}
                <strong>{fmtNum(recommendation.fit_check.estimated_total_gb)} GB</strong>{' '}
                and fits in {recommendation.fit_check.fit_target}. A
                recommendation that failed this check would be advice
                contradicting itself.
              </>
            ) : (
              <>{recommendation.fit_check.reason}</>
            )}
          </p>

          <p className="muted small">
            {dataset.constants.note}. Want the same answer on the command line?{' '}
            <code>aihwbench recommend --vram-mb {vramMb || 0} --ram-gb {ramGb}</code>{' '}
            — see the <Link to="/docs">docs</Link>.
          </p>
        </>
      )}
    </div>
  )
}
