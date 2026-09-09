import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useDataset } from '../lib/useDataset'
import { Loading, ErrorState } from '../components/States'
import { ScatterChart } from '../components/Charts'

// Efficiency frontiers.
//
// A leaderboard answers "which is fastest". A frontier answers "which
// configurations are not beaten on both axes at once", which is the question
// behind an actual purchase: a card that is 10% slower for half the power has
// not lost, and no single ranked column can say so.

const VIEWS = [
  {
    key: 'throughput_vs_power',
    label: 'Speed vs power',
    x: 'Generation tok/s',
    y: 'Average watts',
    blurb:
      'Throughput against power draw. A point that is slower but markedly more efficient is still on the frontier — that is the trade a laptop or an always-on machine actually faces.',
  },
  {
    key: 'throughput_vs_vram',
    label: 'Speed vs VRAM',
    x: 'Generation tok/s',
    y: 'Peak VRAM (MB)',
    blurb:
      'Throughput against peak memory. Lower memory means a bigger model fits alongside, or the same model fits on a smaller card.',
  },
  {
    key: 'throughput_vs_latency',
    label: 'Speed vs first token',
    x: 'Generation tok/s',
    y: 'TTFT (ms)',
    blurb:
      'Sustained throughput against how long the first token takes. Interactive use cares far more about the second than the first.',
  },
] as const

export default function Pareto() {
  const { dataset, loading, error, retry } = useDataset()
  const [view, setView] = useState<(typeof VIEWS)[number]['key']>(
    'throughput_vs_power',
  )

  const current = VIEWS.find((v) => v.key === view) ?? VIEWS[0]
  const frontier = dataset?.pareto?.[view]

  return (
    <div>
      <h1 className="page-title">Efficiency frontiers</h1>
      <p className="page-sub">
        A leaderboard says which result is fastest. A frontier says which
        results are <strong>not beaten on both axes at once</strong> — the
        question behind a purchase, and one a single ranked column cannot
        answer.
      </p>

      {loading && <Loading />}
      {error && <ErrorState message={error} onRetry={retry} />}

      {dataset && (
        <>
          <div className="filter-bar" role="tablist" aria-label="Frontier">
            {VIEWS.map((v) => (
              <button
                key={v.key}
                role="tab"
                aria-selected={view === v.key}
                className={`btn ${view === v.key ? 'primary' : 'secondary'}`}
                onClick={() => setView(v.key)}
              >
                {v.label}
              </button>
            ))}
          </div>
          <p className="muted">{current.blurb}</p>

          {!frontier || frontier.points.length === 0 ? (
            <p className="notice" role="note">
              No published result measured both {current.x.toLowerCase()} and{' '}
              {current.y.toLowerCase()}, so this frontier has nothing to plot.{' '}
              <Link to="/docs">Contributing a result</Link> with power telemetry
              is what fills it in.
            </p>
          ) : (
            <>
              <ScatterChart
                points={frontier.points}
                xLabel={current.x}
                yLabel={current.y}
                yHigherIsBetter={frontier.y_higher_is_better}
              />
              <h2 className="section-title">On the frontier</h2>
              <ul className="measured-list">
                {frontier.points
                  .filter((p) => p.optimal)
                  .map((p) => (
                    <li key={p.run_id}>
                      <Link to={`/results/${p.run_id}`}>{p.run_id}</Link> —{' '}
                      {p.model} on {p.runtime}
                      {p.gpu ? `, ${p.gpu}` : ''}
                    </li>
                  ))}
              </ul>
              {frontier.excluded_missing_metrics > 0 && (
                <p className="muted small">
                  {frontier.excluded_missing_metrics} published result
                  {frontier.excluded_missing_metrics === 1 ? '' : 's'} did not
                  measure both axes and {frontier.excluded_missing_metrics === 1 ? 'is' : 'are'}{' '}
                  excluded — not plotted at zero, which would place them at a
                  corner they did not earn.
                </p>
              )}
            </>
          )}
        </>
      )}
    </div>
  )
}
