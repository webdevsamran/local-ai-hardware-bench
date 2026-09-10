import { useParams, useSearchParams } from 'react-router-dom'
import { useDataset } from '../lib/useDataset'
import { fmtNum } from '../lib/format'
import { SITE_URL } from '../lib/seo'

// A result card sized for someone else's blog post.
//
// The reason this needs care rather than being a styling exercise: a number
// lifted out of this site and dropped into a review article loses everything
// that made it meaningful. "281 tok/s" on its own is the false precision the
// whole project exists to argue against — it says nothing about which model,
// which runtime, which machine, or how much the figure moved between runs.
//
// So the card carries its own context. The hardware and runtime are on it,
// the confidence interval sits with the number where the run measured one,
// the trust state is visible, and the whole thing links back to the full
// result. If a widget cannot fit that, it should not exist.

/** Metrics worth putting in a card this small. */
const HEADLINE_METRICS = [
  { key: 'generation_tokens_per_second', label: 'Generation', unit: 'tok/s' },
  { key: 'ttft_ms', label: 'First token', unit: 'ms' },
  { key: 'average_power_watts', label: 'Power', unit: 'W' },
] as const

export default function EmbedResult() {
  const { runId } = useParams<{ runId: string }>()
  const [params] = useSearchParams()
  const { dataset, loading, error } = useDataset()

  // The host page decides the theme, because the widget sits inside their
  // design rather than ours. Absent the parameter it follows the reader's
  // system preference like every other page.
  const theme = params.get('theme')

  if (loading) return <div className="embed-card embed-empty">Loading…</div>
  if (error || !dataset) {
    return <div className="embed-card embed-empty">Result unavailable.</div>
  }

  const result = dataset.results.find((r) => r.run_id === runId)
  if (!result) {
    return (
      <div className="embed-card embed-empty">
        No published result with id <code>{runId}</code>.
      </div>
    )
  }

  const metrics = result.metrics ?? {}
  const ci = metrics.gen_tps_ci95
  const permalink = `${SITE_URL.replace(/\/$/, '')}/results/${result.run_id}`

  return (
    <div
      className="embed-card"
      data-theme={theme === 'dark' || theme === 'light' ? theme : undefined}
    >
      <div className="embed-head">
        <span className="embed-model">{result.model?.name ?? 'unknown model'}</span>
        <span className={`embed-trust embed-trust-${result.trust_state ?? 'unreviewed'}`}>
          {result.trust_state ?? 'unreviewed'}
        </span>
      </div>

      <dl className="embed-metrics">
        {HEADLINE_METRICS.map(({ key, label, unit }) => {
          const value = metrics[key as keyof typeof metrics] as number | null | undefined
          if (value == null) return null
          return (
            <div key={key}>
              <dt>{label}</dt>
              <dd>
                {fmtNum(value)} <span className="embed-unit">{unit}</span>
                {/* The interval belongs with the number, especially here:
                    this card is the version most likely to be quoted alone. */}
                {key === 'generation_tokens_per_second' && ci && (
                  <span className="embed-ci">
                    95% CI {fmtNum(ci[0])}–{fmtNum(ci[1])}
                  </span>
                )}
              </dd>
            </div>
          )
        })}
      </dl>

      {/* Without this line the card is a number with no experiment attached,
          which is precisely what makes benchmark figures misleading. */}
      <p className="embed-context">
        {result.runtime?.name}
        {result.runtime?.device ? ` (${result.runtime.device})` : ''} on{' '}
        {result.system?.gpu ?? result.system?.cpu ?? 'unknown hardware'}
      </p>

      <p className="embed-caveat">
        Comparable only with results measured on the same model, runtime,
        device and protocol.
      </p>

      <a
        className="embed-link"
        href={permalink}
        target="_blank"
        rel="noopener noreferrer"
      >
        Full result and methodology — AIHWBench
      </a>
    </div>
  )
}
