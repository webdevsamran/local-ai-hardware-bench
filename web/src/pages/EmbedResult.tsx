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

  // These three branches are landmarks but carry no heading, and that is
  // deliberate: none is reachable during prerendering, because the embed
  // routes are generated from the same dataset this card reads. If one ever
  // does land in the static output, the route list and the data have
  // disagreed, and the a11y gate failing on a headingless page is the
  // correct way to find out.
  if (loading) return <main className="embed-card embed-empty">Loading…</main>
  if (error || !dataset) {
    return <main className="embed-card embed-empty">Result unavailable.</main>
  }

  const result = dataset.results.find((r) => r.run_id === runId)
  if (!result) {
    return (
      <main className="embed-card embed-empty">
        No published result with id <code>{runId}</code>.
      </main>
    )
  }

  const metrics = result.metrics ?? {}
  const ci = metrics.gen_tps_ci95
  const permalink = `${SITE_URL.replace(/\/$/, '')}/results/${result.run_id}`

  // `<main>` and `<h1>`, despite this being a card rather than a page.
  //
  // An embed is loaded in an iframe, and an iframe is its own document: a
  // screen reader that enters one gets no landmarks or headings from the host
  // page, so dropping the site chrome dropped the only structure this document
  // had. The heading outline here is separate from the host's, so an `<h1>`
  // names the widget without competing with the article around it. The model
  // name is already the visual title; it just was not marked up as one.
  return (
    <main
      className="embed-card"
      data-theme={theme === 'dark' || theme === 'light' ? theme : undefined}
    >
      <div className="embed-head">
        <h1 className="embed-model">{result.model?.name ?? 'unknown model'}</h1>
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
    </main>
  )
}
