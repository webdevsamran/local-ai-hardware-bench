// Charts that show the *shape* of data, where the ones in Charts.tsx compare
// values. Dependency-free SVG, same as the rest.
//
// An **area** chart says "this accumulates" where a line says "this varies" —
// right for a cumulative quantity like energy across a run, wrong for a rate.
//
// A **heatmap** is the only honest rendering of a two-axis sweep. The KV-cache
// matrix is nine cells over K dtype and V dtype; flattening it into bars
// throws away which axis moved, and the two inversions in that matrix are
// visible precisely because they sit at one end of one axis.
//
// A **violin** shows a distribution rather than its middle. Iteration
// throughput on a thermally limited laptop is bimodal — fast before the
// throttle, slow after — and the mean lands between two values the machine
// never sustained. That exact failure is why the sustained workload exists,
// and a bar chart of means cannot show it.

export interface AreaPoint {
  label: string
  value: number
}

export function AreaChart({
  data,
  unit,
  height = 200,
  cumulative = false,
}: {
  data: AreaPoint[]
  unit?: string
  height?: number
  /** Plot the running total rather than each value. */
  cumulative?: boolean
}) {
  if (data.length < 2) return null

  const values = cumulative
    ? data.reduce<number[]>((acc, d) => [...acc, (acc[acc.length - 1] ?? 0) + d.value], [])
    : data.map((d) => d.value)
  const max = Math.max(...values)
  const min = Math.min(0, ...values)
  const span = max - min || 1
  const step = 100 / (values.length - 1)

  const points = values.map((v, i) => `${i * step},${100 - ((v - min) / span) * 100}`)
  // Closed back along the baseline so the fill has a floor. An unclosed path
  // fills to wherever the last point happens to sit, which looks deliberate
  // and is meaningless.
  const area = `M0,100 L${points.join(' L')} L100,100 Z`

  return (
    <figure className="chart">
      <svg
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
        style={{ height, width: '100%' }}
        role="img"
        aria-label={`Area chart${unit ? ` in ${unit}` : ''}${cumulative ? ', cumulative' : ''}`}
      >
        <path d={area} className="area-fill" />
        <polyline points={points.join(' ')} className="area-line" fill="none" />
      </svg>
      <figcaption className="muted">
        Max {max.toFixed(max < 10 ? 2 : 0)}
        {unit ? ` ${unit}` : ''}
        {cumulative ? ' (running total)' : ''}
      </figcaption>
      {/* The numbers themselves, for a screen reader: a described picture is
          not the data, and every chart here has a table behind it. */}
      <table className="visually-hidden">
        <caption>{cumulative ? 'Cumulative values' : 'Values'}</caption>
        <tbody>
          {data.map((d, i) => (
            <tr key={d.label}>
              <th scope="row">{d.label}</th>
              <td>
                {(values[i] ?? 0).toFixed(2)}
                {unit ? ` ${unit}` : ''}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  )
}

export interface HeatmapCell {
  row: string
  column: string
  value: number | null
  /** Shown on hover when a cell needs a caveat. */
  note?: string
}

export function Heatmap({
  cells,
  rowLabel,
  columnLabel,
  unit,
  lowerIsBetter = false,
}: {
  cells: HeatmapCell[]
  rowLabel: string
  columnLabel: string
  unit?: string
  lowerIsBetter?: boolean
}) {
  if (cells.length === 0) return null

  const rows = [...new Set(cells.map((c) => c.row))]
  const columns = [...new Set(cells.map((c) => c.column))]
  const measured = cells.filter((c) => typeof c.value === 'number').map((c) => c.value as number)
  if (measured.length === 0) return null

  const min = Math.min(...measured)
  const max = Math.max(...measured)
  const span = max - min || 1
  const lookup = new Map(cells.map((c) => [`${c.row}|${c.column}`, c]))

  return (
    <figure className="chart">
      <div className="table-wrap">
        <table className="heatmap data-table">
          <caption className="visually-hidden">
            {rowLabel} against {columnLabel}
            {unit ? `, in ${unit}` : ''}
          </caption>
          <thead>
            <tr>
              <th scope="col">
                {rowLabel} / {columnLabel}
              </th>
              {columns.map((c) => (
                <th scope="col" key={c} className="numeric">
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r}>
                <th scope="row">{r}</th>
                {columns.map((c) => {
                  const cell = lookup.get(`${r}|${c}`)
                  const value = cell?.value
                  if (typeof value !== 'number') {
                    // Unmeasured, not zero. A blank cell and a cold cell mean
                    // different things and must not share an appearance.
                    return (
                      <td
                        key={c}
                        className="heat-missing numeric"
                        title={cell?.note ?? 'not measured'}
                      >
                        —
                      </td>
                    )
                  }
                  const normalized = (value - min) / span
                  const intensity = lowerIsBetter ? 1 - normalized : normalized
                  return (
                    <td
                      key={c}
                      className="heat-cell numeric"
                      // Opacity of one accent rather than a hue ramp: it
                      // survives both themes and every colour-vision
                      // difference, and the number is in the cell regardless
                      // so the colour is never the only carrier.
                      style={{ ['--heat' as string]: intensity.toFixed(3) }}
                      title={cell?.note ?? undefined}
                    >
                      {value.toFixed(value < 10 ? 2 : 0)}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <figcaption className="muted">
        {unit ? `${unit}. ` : ''}
        Darker is {lowerIsBetter ? 'lower' : 'higher'}. A cell marked — was not
        measured, which is not the same as zero.
      </figcaption>
    </figure>
  )
}

export interface ViolinSeries {
  label: string
  values: number[]
}

export function ViolinChart({
  series,
  unit,
  height = 220,
}: {
  series: ViolinSeries[]
  unit?: string
  height?: number
}) {
  // Fewer than four points describes no distribution; drawing one would imply
  // a shape the data cannot support.
  const usable = series.filter((s) => s.values.length >= 4)
  if (usable.length === 0) return null

  const all = usable.flatMap((s) => s.values)
  const min = Math.min(...all)
  const max = Math.max(...all)
  const span = max - min || 1

  const BINS = 14
  const slot = 100 / usable.length

  return (
    <figure className="chart">
      <svg
        viewBox="0 0 100 60"
        style={{ height, width: '100%' }}
        role="img"
        aria-label={`Distribution of ${usable.length} series${unit ? ` in ${unit}` : ''}`}
      >
        {usable.map((s, index) => {
          const centre = slot * (index + 0.5)
          const counts: number[] = new Array(BINS).fill(0)
          for (const v of s.values) {
            const bin = Math.min(BINS - 1, Math.max(0, Math.floor(((v - min) / span) * BINS)))
            counts[bin] = (counts[bin] ?? 0) + 1
          }
          const peak = Math.max(...counts) || 1
          const halfMax = slot * 0.42

          const left = counts.map((count, b) => {
            const y = 56 - (b / (BINS - 1)) * 52
            return `${centre - (count / peak) * halfMax},${y}`
          })
          const right = counts
            .map((count, b) => {
              const y = 56 - (b / (BINS - 1)) * 52
              return `${centre + (count / peak) * halfMax},${y}`
            })
            .reverse()

          const sorted = [...s.values].sort((a, b) => a - b)
          const median = sorted[Math.floor(sorted.length / 2)] ?? min
          const medianY = 56 - ((median - min) / span) * 52

          return (
            <g key={s.label}>
              <polygon points={[...left, ...right].join(' ')} className="violin-body" />
              <line
                x1={centre - halfMax}
                x2={centre + halfMax}
                y1={medianY}
                y2={medianY}
                className="violin-median"
              />
            </g>
          )
        })}
      </svg>
      <div className="violin-axis" aria-hidden="true">
        {usable.map((s) => (
          <span key={s.label}>{s.label}</span>
        ))}
      </div>
      <figcaption className="muted">
        The shape is where the iterations landed; the line is the median. Two
        lobes mean the machine ran at two speeds, and its mean sits between them
        at a rate it never sustained.
      </figcaption>
      <table className="visually-hidden">
        <caption>Distribution summary</caption>
        <tbody>
          {usable.map((s) => {
            const sorted = [...s.values].sort((a, b) => a - b)
            return (
              <tr key={s.label}>
                <th scope="row">{s.label}</th>
                <td>
                  {sorted.length} iterations, min {(sorted[0] ?? 0).toFixed(1)}, median{' '}
                  {(sorted[Math.floor(sorted.length / 2)] ?? 0).toFixed(1)}, max{' '}
                  {(sorted[sorted.length - 1] ?? 0).toFixed(1)}
                  {unit ? ` ${unit}` : ''}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </figure>
  )
}
