import { useState } from 'react'
import { useDataset } from '../lib/useDataset'
import { Loading, ErrorState } from '../components/States'
import { Heatmap } from '../components/Distributions'
import { fmtInt, fmtNum } from '../lib/format'
import type { KvCacheConfiguration } from '../lib/types'

// KV-cache quantization, reported as a memory setting rather than a speed one.
//
// The usual framing is the problem. Measured as throughput, quantizing the
// cache looks like a small loss and the advice is to leave it alone. Measured
// as memory, it is what decides whether a long conversation fits at all — and
// on this machine the best configuration turned out to cost nothing in speed
// while cutting the cache by 72%.
//
// Two of the nine configurations measured use *more* device memory than the
// f16 baseline despite holding a smaller cache. That inversion is invisible to
// the arithmetic and only shows up if you measure, which is the argument for
// this whole project in one table.

/** ggml block sizes: a quantized cache carries scales, so it is not 4 bits. */
const BYTES_PER_ELEMENT: Record<string, number> = {
  f16: 2,
  bf16: 2,
  q8_0: 34 / 32,
  q5_1: 24 / 32,
  q5_0: 22 / 32,
  q4_1: 20 / 32,
  q4_0: 18 / 32,
}

const MIB = 1024 * 1024

function cacheBytesPerToken(
  geometry: Record<string, number | string | null> | null,
  dtype: string,
): number | null {
  if (!geometry) return null
  const layers = Number(geometry.block_count)
  const heads = Number(geometry.head_count_kv)
  const width = Number(geometry.head_dim)
  const size = BYTES_PER_ELEMENT[dtype]
  if (!layers || !heads || !width || !size) return null
  // Both K and V, hence the doubling.
  return layers * heads * width * size * 2
}

function Row({ config }: { config: KvCacheConfiguration }) {
  const change = config.throughput_change_percent
  return (
    <tr className={config.costs_more_than_baseline ? 'kv-inverted' : undefined}>
      <td>
        <code>
          {config.cache_type_k}/{config.cache_type_v}
        </code>
        {config.is_baseline && <span className="muted"> (default)</span>}
      </td>
      <td className="numeric">{fmtNum(config.kv_cache_mb)}</td>
      <td className="numeric">
        {/* The baseline is not 0% smaller than itself; it is the thing being
            compared against, and "−0.0%" reads as a measurement. */}
        {config.is_baseline || config.kv_cache_saved_percent == null
          ? '—'
          : `−${config.kv_cache_saved_percent.toFixed(1)}%`}
      </td>
      <td className="numeric">
        {fmtNum(config.peak_vram_mb)}
        {config.costs_more_than_baseline && (
          <span className="kv-warn" title={config.measurement_note}>
            {' '}
            ⚠
          </span>
        )}
      </td>
      <td className="numeric">{fmtNum(config.generation_tokens_per_second)}</td>
      <td className="numeric">
        {change == null ? (
          '—'
        ) : config.throughput_distinguishable ? (
          <strong>{change.toFixed(1)}%</strong>
        ) : (
          <span className="muted" title={config.throughput_note}>
            {change > 0 ? '+' : ''}
            {change.toFixed(1)}% ≈
          </span>
        )}
      </td>
    </tr>
  )
}

export default function KvCache() {
  const { dataset, loading, error, retry } = useDataset()
  const [budgetGb, setBudgetGb] = useState(1)

  return (
    <div>
      <h1 className="page-title">KV-cache quantization</h1>
      <p className="page-sub">
        How much context fits on your card — <strong>measured</strong>. Quantizing
        the KV cache is a memory setting, not a speed one, and reading it as a
        speed setting leads to the opposite advice.
      </p>

      {loading && <Loading />}
      {error && <ErrorState message={error} onRetry={retry} />}

      {dataset && dataset.kvcache.studies.length === 0 && (
        <p className="notice" role="note">
          No KV-cache sweep has been published yet. Running{' '}
          <code>
            aihwbench sweep --cache-type-k-list f16,q8_0,q4_0 --cache-type-v-list
            f16,q8_0,q4_0
          </code>{' '}
          on your own hardware is what puts a table here.
        </p>
      )}

      {dataset?.kvcache.studies.map((study) => {
        const report = study.report
        const inverted = report.configurations.filter(
          (c) => c.costs_more_than_baseline,
        )
        const best = report.configurations.find(
          (c) => !c.is_baseline && c.throughput_distinguishable === false,
        )
        const perToken = {
          f16: cacheBytesPerToken(report.geometry, 'f16'),
          q4_0: cacheBytesPerToken(report.geometry, 'q4_0'),
        }
        const budgetBytes = budgetGb * 1024 * MIB

        return (
          <section className="card" key={study.source}>
            <h2>
              {study.model} on {study.gpu ?? 'unknown hardware'}
            </h2>
            <p className="muted">
              {study.runtime}
              {report.context_length
                ? `, ${fmtInt(report.context_length)} token context`
                : ''}
              {study.timestamp ? ` · measured ${study.timestamp.slice(0, 10)}` : ''}
            </p>

            {best && (
              <p className="kv-verdict">
                Best measured: <code>{best.cache_type_k}/{best.cache_type_v}</code> —{' '}
                {best.kv_cache_saved_percent?.toFixed(1)}% less cache, and a
                generation rate indistinguishable from the <code>f16</code>{' '}
                default.
              </p>
            )}

            <div className="table-wrap">
              <table className="data-table">
                <caption className="visually-hidden">
                  KV-cache dtype configurations with computed cache size, measured
                  device VRAM and generation throughput
                </caption>
                <thead>
                  <tr>
                    <th scope="col">K/V dtype</th>
                    <th scope="col" className="numeric">
                      Cache (MiB)
                    </th>
                    <th scope="col" className="numeric">
                      vs f16
                    </th>
                    <th scope="col" className="numeric">
                      Device VRAM (MiB)
                    </th>
                    <th scope="col" className="numeric">
                      tok/s
                    </th>
                    <th scope="col" className="numeric">
                      vs f16
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {report.configurations.map((config) => (
                    <Row
                      config={config}
                      key={`${config.cache_type_k}-${config.cache_type_v}`}
                    />
                  ))}
                </tbody>
              </table>
            </div>
            {/* The same nine numbers as a grid. The table reads one row at a
                time; the grid shows that both outliers sit in one column,
                which is the finding -- K quantized against V at f16. */}
            <Heatmap
              cells={report.configurations.map((c) => ({
                row: `K ${c.cache_type_k}`,
                column: `V ${c.cache_type_v}`,
                value: c.peak_vram_mb,
                note: c.costs_more_than_baseline
                  ? 'uses more memory than the f16 default despite a smaller cache'
                  : undefined,
              }))}
              rowLabel="K"
              columnLabel="V"
              unit="device VRAM, MiB"
              lowerIsBetter
            />

            <p className="muted note">
              ≈ marks a throughput difference inside the run-to-run noise floor:
              indistinguishable from the default, which is not the same as equal
              to it. The cache column is computed from the model's attention
              geometry as its own file states it. The VRAM column is the whole
              device, including anything else resident.
            </p>

            {inverted.length > 0 && (
              <div className="notice" role="note">
                <strong>
                  {inverted.length === 1
                    ? 'One configuration uses'
                    : `${inverted.length} configurations use`}{' '}
                  more memory than the default despite holding a smaller cache.
                </strong>
                <ul>
                  {inverted.map((c) => (
                    <li key={`${c.cache_type_k}-${c.cache_type_v}`}>
                      <code>
                        {c.cache_type_k}/{c.cache_type_v}
                      </code>{' '}
                      used{' '}
                      <strong>
                        {Math.abs(c.measured_vram_saved_mb ?? 0).toFixed(0)} MiB more
                      </strong>{' '}
                      than <code>f16/f16</code>, against a predicted saving of{' '}
                      {c.kv_cache_saved_mb?.toFixed(0)} MiB.
                    </li>
                  ))}
                </ul>
                <p className="note">
                  The cause on this machine was <code>--flash-attn</code>, whose
                  default is <code>auto</code> — and auto is not a synonym for on.
                  llama.cpp declined flash attention for these dtype pairs, and the
                  fallback path allocated the difference. Forcing{' '}
                  <code>--flash-attn on</code> brought the same configuration to 902
                  MiB, below the <code>f16</code> baseline and in line with the cache
                  arithmetic. Use matching dtypes for K and V; if you use a mismatched
                  pair anyway, set the flag explicitly rather than trusting{' '}
                  <code>auto</code>.
                </p>
              </div>
            )}

            {perToken.f16 && perToken.q4_0 && (
              <div className="kv-budget">
                <h3>What a VRAM budget buys</h3>
                <label htmlFor="kv-budget">
                  VRAM available for the cache: <strong>{budgetGb} GB</strong>
                </label>
                <input
                  id="kv-budget"
                  type="range"
                  min={1}
                  max={16}
                  step={1}
                  value={budgetGb}
                  onChange={(e) => setBudgetGb(Number(e.target.value))}
                />
                <dl className="zoo-facts">
                  <dt>
                    At <code>f16</code>
                  </dt>
                  <dd>
                    {fmtInt(Math.floor(budgetBytes / perToken.f16))} tokens
                  </dd>
                  <dt>
                    At <code>q4_0</code>
                  </dt>
                  <dd>
                    {fmtInt(Math.floor(budgetBytes / perToken.q4_0))} tokens
                  </dd>
                </dl>
                <p className="muted note">
                  Computed from this model's attention geometry, so it holds at
                  context lengths nobody has run. It counts the cache only — the
                  weights need their own room.
                </p>
              </div>
            )}
          </section>
        )
      })}

      {dataset && dataset.kvcache.studies.length > 0 && (
        <section className="card">
          <h2>Reading this</h2>
          <p>{dataset.kvcache.note}</p>
          <p className="muted note">
            None of this measures whether the answers got worse. Quantizing the
            cache changes what the model computes, and these numbers are about
            memory and speed only.
          </p>
        </section>
      )}
    </div>
  )
}
