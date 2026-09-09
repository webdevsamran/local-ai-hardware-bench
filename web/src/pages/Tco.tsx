import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useDataset } from '../lib/useDataset'
import { Loading, ErrorState } from '../components/States'
import { compareLocalVsCloud } from '../lib/tco'
import { fmtNum } from '../lib/format'

// "Should I buy hardware or keep paying an API?" is a decision, not a
// benchmark — but it is the decision the benchmark data exists to inform, and
// it is only answerable with measured power and throughput.
//
// No cloud price is bundled. Provider prices change often, and a static site
// carrying a stale table would go on giving confident wrong answers.

/** Money, with the sign outside the currency symbol: -$1,586.22, not $-1,586.22. */
const usd = (value: number | null | undefined) => {
  if (value == null) return '—'
  const amount = Math.abs(value).toLocaleString('en-US', { maximumFractionDigits: 2 })
  return `${value < 0 ? '-' : ''}$${amount}`
}

export default function Tco() {
  const { dataset, loading, error, retry } = useDataset()

  const [tokensPerMonth, setTokensPerMonth] = useState(10_000_000)
  const [cloudPrice, setCloudPrice] = useState(0.6)
  const [hardwareCost, setHardwareCost] = useState(1800)
  const [electricity, setElectricity] = useState(0.3)
  const [years, setYears] = useState(3)
  const [runId, setRunId] = useState('')

  // Results that measured both power and throughput can seed the local side.
  const usable = useMemo(
    () =>
      (dataset?.results ?? []).filter(
        (r) =>
          r.metrics?.average_power_watts != null &&
          r.metrics?.generation_tokens_per_second != null,
      ),
    [dataset],
  )

  const selected = usable.find((r) => r.run_id === runId) ?? usable[0]
  const watts = selected?.metrics?.average_power_watts ?? null
  const tps = selected?.metrics?.generation_tokens_per_second ?? null

  const report = useMemo(
    () =>
      compareLocalVsCloud({
        tokensPerMonth,
        cloudUsdPerMillionTokens: cloudPrice,
        hardwareCostUsd: hardwareCost,
        electricityUsdPerKwh: electricity,
        averagePowerWatts: watts,
        generationTokensPerSecond: tps,
        years,
      }),
    [tokensPerMonth, cloudPrice, hardwareCost, electricity, watts, tps, years],
  )

  return (
    <div>
      <h1 className="page-title">Local hardware vs a cloud API</h1>
      <p className="page-sub">
        Whether buying hardware costs less than paying per token, using{' '}
        <strong>measured</strong> power draw and throughput from a published
        result rather than a nameplate rating.
      </p>

      {loading && <Loading />}
      {error && <ErrorState message={error} onRetry={retry} />}

      {dataset && (
        <>
          <div className="wizard-grid">
            <label className="field">
              <span className="field-label">Tokens per month</span>
              <input
                type="number"
                min={0}
                step={1_000_000}
                value={tokensPerMonth}
                onChange={(e) => setTokensPerMonth(Number(e.target.value))}
              />
            </label>

            <label className="field">
              <span className="field-label">Cloud price (USD / M tokens)</span>
              <input
                type="number"
                min={0}
                step={0.05}
                value={cloudPrice}
                onChange={(e) => setCloudPrice(Number(e.target.value))}
              />
            </label>

            <label className="field">
              <span className="field-label">Hardware cost (USD)</span>
              <input
                type="number"
                min={0}
                step={50}
                value={hardwareCost}
                onChange={(e) => setHardwareCost(Number(e.target.value))}
              />
            </label>

            <label className="field">
              <span className="field-label">Electricity (USD / kWh)</span>
              <input
                type="number"
                min={0}
                step={0.01}
                value={electricity}
                onChange={(e) => setElectricity(Number(e.target.value))}
              />
            </label>

            <label className="field">
              <span className="field-label">Horizon (years)</span>
              <input
                type="number"
                min={1}
                max={10}
                value={years}
                onChange={(e) => setYears(Number(e.target.value))}
              />
            </label>

            {usable.length > 0 && (
              <label className="field">
                <span className="field-label">Measured from</span>
                <select
                  value={selected?.run_id ?? ''}
                  onChange={(e) => setRunId(e.target.value)}
                >
                  {usable.map((r) => (
                    <option key={r.run_id} value={r.run_id}>
                      {r.run_id}
                    </option>
                  ))}
                </select>
              </label>
            )}
          </div>

          {usable.length === 0 ? (
            <p className="notice" role="note">
              No published result measured both power draw and throughput, so
              the local running cost cannot be computed from data.{' '}
              <Link to="/docs">Contributing a result</Link> with power telemetry
              is what makes this answerable.
            </p>
          ) : (
            <>
              <div
                className={`verdict verdict-${
                  report.cheaper === 'local' ? 'ok' : report.cheaper === 'cloud' ? 'warn' : 'unknown'
                }`}
                role="status"
              >
                <h2 className="verdict-headline">
                  {report.cheaper === 'local'
                    ? `Owning the hardware is cheaper over ${years} year${years === 1 ? '' : 's'}`
                    : report.cheaper === 'cloud'
                      ? `Paying the API is cheaper over ${years} year${years === 1 ? '' : 's'}`
                      : 'Not enough information'}
                </h2>
                <p className="verdict-detail">
                  {report.break_even_months == null
                    ? (report.reason ??
                      'At this volume the hardware never pays for itself.')
                    : `Hardware pays for itself after about ${report.break_even_months} months at this volume.`}
                </p>
                <dl className="verdict-figures">
                  <div>
                    <dt>Cloud, {years}y</dt>
                    <dd>{usd(report.cloud_cost_usd)}</dd>
                  </div>
                  <div>
                    <dt>Local, {years}y</dt>
                    <dd>{usd(report.local_cost_usd)}</dd>
                  </div>
                  <div>
                    <dt>Of which electricity</dt>
                    <dd>{usd(report.local_energy_usd)}</dd>
                  </div>
                  <div>
                    <dt>Difference</dt>
                    <dd>{usd(report.savings_usd)}</dd>
                  </div>
                </dl>
              </div>

              <p className="muted small">
                Local running cost uses{' '}
                <strong>{fmtNum(watts)} W</strong> and{' '}
                <strong>{fmtNum(tps)} tok/s</strong> measured on{' '}
                <Link to={`/results/${selected?.run_id}`}>{selected?.run_id}</Link>.
                Cloud pricing is yours to supply — this site bundles none,
                because provider prices change and a stale figure here would
                quietly mislead. It also ignores everything that is not
                electricity or purchase price: your time, cooling, failure
                rates, and the fact that a cloud API needs no capital up front.
              </p>
            </>
          )}
        </>
      )}
    </div>
  )
}
