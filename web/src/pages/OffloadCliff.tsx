import { Link } from 'react-router-dom'
import { useDataset } from '../lib/useDataset'
import { Loading, ErrorState } from '../components/States'
import { MeasuredCliffChart } from '../components/Charts'
import { fmtNum } from '../lib/format'

// What offloading actually costs, measured.
//
// The fit estimator on /will-it-run answers a memory question: how much of a
// model would spill out of VRAM. This page answers the question that follows,
// and the one people actually care about — what that spill does to throughput.
// The two are not the same shape. Memory pressure rises smoothly; throughput
// falls off a step.
//
// It is also the clearest case for a crowdsourced dataset over a vendor one.
// Where the cliff sits depends on PCIe generation and width, memory bandwidth,
// and how much VRAM the desktop is already using — so the answer is different
// on every machine, and no amount of vendor testing produces yours.

export default function OffloadCliff() {
  const { dataset, loading, error, retry } = useDataset()

  return (
    <div>
      <h1 className="page-title">The offload cliff</h1>
      <p className="page-sub">
        What happens to throughput as layers move off the GPU —{' '}
        <strong>measured</strong>, not estimated. Throughput does not degrade
        smoothly as a model stops fitting in VRAM; it falls off a step, and
        where that step sits is a property of your machine.
      </p>

      {loading && <Loading />}
      {error && <ErrorState message={error} onRetry={retry} />}

      {dataset && dataset.cliff.curves.length === 0 && (
        <p className="notice" role="note">
          No offload sweep has been published yet. Running{' '}
          <code>aihwbench sweep --gpu-layers-list 0,8,16,24,99</code> on your
          own hardware is what puts a curve here.
        </p>
      )}

      {dataset?.cliff.curves.map((curve) => {
        const analysis = curve.analysis
        return (
          <section className="card" key={curve.source}>
            <h2>
              {curve.model} on {curve.gpu ?? curve.cpu ?? 'unknown hardware'}
            </h2>
            <p className="muted">
              {curve.runtime}
              {curve.gpu_vram_mb
                ? `, ${(curve.gpu_vram_mb / 1024).toFixed(0)} GB VRAM`
                : ''}
              {curve.timestamp ? ` · measured ${curve.timestamp.slice(0, 10)}` : ''}
            </p>

            <MeasuredCliffChart points={curve.points} />

            <div
              className={`verdict verdict-${analysis.cliff_detected ? 'warn' : 'ok'}`}
              role="status"
            >
              <h3 className="verdict-headline">
                {analysis.cliff_detected
                  ? `A ${Math.round((analysis.largest_drop_fraction ?? 0) * 100)}% drop between ${analysis.cliff_between_layers?.[0]} and ${analysis.cliff_between_layers?.[1]} layers`
                  : 'No cliff in this range'}
              </h3>
              <dl className="verdict-figures">
                <div>
                  <dt>Fastest setting</dt>
                  <dd>{analysis.best_layers} layers</dd>
                </div>
                <div>
                  <dt>At</dt>
                  <dd>{fmtNum(analysis.best_tokens_per_second)} tok/s</dd>
                </div>
                <div>
                  <dt>Points measured</dt>
                  <dd>{analysis.points}</dd>
                </div>
              </dl>
              {/* A "fastest" that ties with another setting is a sort order.
                  Saying so is the same discipline the leaderboard applies. */}
              {analysis.best_is_tied_with && analysis.best_is_tied_with.length > 0 && (
                <p className="verdict-detail">
                  Not distinguishable from{' '}
                  {analysis.best_is_tied_with.join(', ')} layers (
                  {analysis.tie_basis}). Pinning one over the other would be
                  tuning against the noise floor.
                </p>
              )}
            </div>

            <h3>Every measured point</h3>
            {/* Scrolls on its own rather than widening the page: at 320px a
                four-column table otherwise makes the whole body scroll
                sideways, dragging the prose along with it. */}
            <div className="table-wrap">
              <table className="data-table">
                <caption className="visually-hidden">
                  Measured generation throughput and peak VRAM at each offload
                  setting
                </caption>
                <thead>
                  <tr>
                    <th scope="col">GPU layers</th>
                    <th scope="col">Generation</th>
                    <th scope="col">95% CI</th>
                    <th scope="col">Peak VRAM</th>
                  </tr>
                </thead>
                <tbody>
                  {curve.points.map((point) => (
                    <tr key={point.gpu_layers}>
                      <td>{point.gpu_layers}</td>
                      <td>{fmtNum(point.tokens_per_second)} tok/s</td>
                      <td>
                        {point.ci95
                          ? `${fmtNum(point.ci95[0])} – ${fmtNum(point.ci95[1])}`
                          : '—'}
                      </td>
                      <td>{fmtNum(point.peak_vram_mb)} MB</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )
      })}

      {dataset && dataset.cliff.curves.length > 0 && (
        <>
          <h2 className="section-title">How to read this</h2>
          <p className="muted">{dataset.cliff.note}</p>
          <p className="muted">
            A curve measured on a small model shows the cost of{' '}
            <em>splitting</em> work across the PCIe bus. It does not show what
            happens when a model genuinely exhausts the card, which is the
            harder and more punishing case — mapping that needs a model large
            enough to fill the VRAM. Treat these as something to compare your
            own measurement against, not as a figure to cite.
          </p>
          <p className="muted small">
            Want the curve for your machine?{' '}
            <code>
              aihwbench sweep --runtime llama.cpp --model-path &lt;model&gt;.gguf
              --gpu-layers-list 0,8,16,24,99 --iterations-list 8
            </code>{' '}
            then <code>aihwbench cliff &lt;sweep&gt;.json</code>. See{' '}
            <Link to="/will-it-run">the fit estimator</Link> for the memory
            question this one follows from.
          </p>
        </>
      )}
    </div>
  )
}
