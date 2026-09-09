// Dependency-free SVG charts. Only rendered when real data exists —
// charts never invent values for missing points.

interface BarDatum {
  label: string
  value: number
}

export function BarChart({
  data,
  unit,
  height = 220,
}: {
  data: BarDatum[]
  unit?: string
  height?: number
}) {
  if (data.length === 0) return null
  const max = Math.max(...data.map((d) => d.value))
  const barW = 100 / data.length
  return (
    <figure className="chart">
      <svg
        viewBox={`0 0 100 ${height}`}
        role="img"
        aria-label={`Bar chart${unit ? ` in ${unit}` : ''}`}
        preserveAspectRatio="none"
        style={{ width: '100%', height }}
      >
        {data.map((d, i) => {
          const h = (d.value / max) * (height - 24)
          return (
            <g key={i}>
              <rect
                x={i * barW + barW * 0.15}
                y={height - 20 - h}
                width={barW * 0.7}
                height={h}
                rx={1}
                className="bar"
              />
              <text
                x={i * barW + barW / 2}
                y={height - 6}
                textAnchor="middle"
                className="chart-label"
              >
                {d.label.length > 10 ? d.label.slice(0, 9) + '…' : d.label}
              </text>
            </g>
          )
        })}
      </svg>
      <figcaption className="muted">
        Max value: {max.toLocaleString('en-US')}
        {unit ? ` ${unit}` : ''}
      </figcaption>
    </figure>
  )
}

export interface LinePoint {
  label: string
  value: number | null | undefined
}

export function LineChart({
  series,
  unit,
  height = 200,
}: {
  series: { name: string; points: LinePoint[] }[]
  unit?: string
  height?: number
}) {
  const all = series.flatMap((s) => s.points.map((p) => p.value))
  const nums = all.filter((v): v is number => v !== null && v !== undefined)
  if (nums.length === 0) return null
  const max = Math.max(...nums)
  const min = Math.min(...nums)
  const span = max - min || 1

  return (
    <figure className="chart">
      <svg
        viewBox={`0 0 100 ${height}`}
        role="img"
        aria-label={`Line chart${unit ? ` in ${unit}` : ''}`}
        preserveAspectRatio="none"
        style={{ width: '100%', height }}
      >
        {[0.25, 0.5, 0.75].map((f) => (
          <line
            key={f}
            x1={0}
            x2={100}
            y1={height * f}
            y2={height * f}
            className="gridline"
          />
        ))}
        {series.map((s, si) => {
          const n = s.points.length
          if (n === 0) return null
          const coords = s.points
            .map((p, i) => {
              if (p.value === null || p.value === undefined) return null
              const x = n === 1 ? 50 : (i / (n - 1)) * 96 + 2
              const y = height - 16 - ((p.value - min) / span) * (height - 32)
              return `${x},${y}`
            })
            .filter((c): c is string => c !== null)
          if (coords.length === 0) return null
          return (
            <polyline
              key={si}
              points={coords.join(' ')}
              fill="none"
              strokeWidth={1.2}
              className={`line line-${si % 4}`}
            />
          )
        })}
      </svg>
      <figcaption className="muted">
        Range: {min.toLocaleString('en-US')} – {max.toLocaleString('en-US')}
        {unit ? ` ${unit}` : ''} ·{' '}
        {series.map((s) => s.name).join(', ')}
      </figcaption>
    </figure>
  )
}

export function HBar({
  value,
  max,
  label,
}: {
  value: number
  max: number
  label: string
}) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0
  return (
    <div className="hbar" role="img" aria-label={`${label}: ${pct.toFixed(0)}%`}>
      <div className="hbar-fill" style={{ width: `${pct}%` }} />
    </div>
  )
}
export interface CliffPoint {
  /** VRAM in GB. */
  vramGb: number
  /** Fraction of the model that must live outside VRAM, 0..1. */
  offload: number
}

/**
 * The VRAM cliff: how much of a model spills out of GPU memory as VRAM shrinks.
 *
 * The shape is the point. Offload is zero up to the moment the model no longer
 * fits, and then climbs — and that transition is where throughput collapses.
 * Drawing it makes the discontinuity obvious in a way a single "fits / does
 * not fit" verdict cannot.
 *
 * The curve is arithmetic on an estimate, not measured throughput, and the
 * caption says so.
 */
export function CliffChart({
  points,
  requiredGb,
  currentGb,
  height = 200,
}: {
  points: CliffPoint[]
  requiredGb: number
  currentGb: number | null
  height?: number
}) {
  if (points.length < 2) return null

  const maxVram = Math.max(...points.map((p) => p.vramGb))
  const padLeft = 8
  const padBottom = 22
  const plotW = 100 - padLeft
  const plotH = height - padBottom

  const x = (vramGb: number) => padLeft + (vramGb / maxVram) * plotW
  const y = (offload: number) => plotH - offload * (plotH - 8)

  const path = points
    .map((p, i) => `${i === 0 ? 'M' : 'L'} ${x(p.vramGb).toFixed(2)} ${y(p.offload).toFixed(2)}`)
    .join(' ')

  const fitsAt = requiredGb
  return (
    <figure className="chart">
      <svg
        viewBox={`0 0 100 ${height}`}
        role="img"
        aria-label={
          `Share of the model running outside VRAM, against GPU memory size. ` +
          `It fits entirely at about ${fitsAt.toFixed(1)} gigabytes.`
        }
        preserveAspectRatio="none"
        style={{ width: '100%', height }}
      >
        {/* Fully-resident region: everything at or above the requirement. */}
        <rect
          x={x(fitsAt)}
          y={0}
          width={Math.max(0, 100 - x(fitsAt))}
          height={plotH}
          className="cliff-safe"
        />
        <path d={path} className="cliff-line" vectorEffect="non-scaling-stroke" />
        {/* The cliff edge itself. */}
        <line
          x1={x(fitsAt)}
          x2={x(fitsAt)}
          y1={0}
          y2={plotH}
          className="cliff-edge"
          vectorEffect="non-scaling-stroke"
        />
        {currentGb !== null && currentGb > 0 && (
          <line
            x1={x(currentGb)}
            x2={x(currentGb)}
            y1={0}
            y2={plotH}
            className="cliff-you"
            vectorEffect="non-scaling-stroke"
          />
        )}
        <text x={padLeft} y={height - 6} className="chart-label">
          0 GB
        </text>
        <text x={98} y={height - 6} textAnchor="end" className="chart-label">
          {maxVram.toFixed(0)} GB
        </text>
      </svg>
      <figcaption className="muted">
        Share of the model outside VRAM as GPU memory varies. It becomes fully
        resident at about <strong>{fitsAt.toFixed(1)} GB</strong>
        {currentGb !== null && currentGb > 0 ? (
          <> — the second line marks your {currentGb.toFixed(0)} GB.</>
        ) : (
          '.'
        )}{' '}
        Estimated from parameter count and quantization, not measured
        throughput.
      </figcaption>
    </figure>
  )
}

export interface ScatterPoint {
  run_id: string
  x: number
  y: number
  label?: string | null
  optimal?: boolean
}

/**
 * Scatter plot with the Pareto-optimal points marked.
 *
 * A ranked column can only answer "which is fastest". A frontier answers
 * "which configurations are not beaten on both axes at once", which is the
 * question behind an actual purchase — a card that is slightly slower but
 * draws half the power has not lost, and a single ranking cannot say so.
 *
 * Optimal points are given a distinct shape as well as a colour, so the
 * distinction survives for a reader who cannot separate the two hues.
 */
export function ScatterChart({
  points,
  xLabel,
  yLabel,
  yHigherIsBetter = false,
  height = 260,
}: {
  points: ScatterPoint[]
  xLabel: string
  yLabel: string
  yHigherIsBetter?: boolean
  height?: number
}) {
  if (points.length === 0) return null

  // A fixed 100x60 viewBox with the default `meet` aspect ratio, rather than
  // the stretched `preserveAspectRatio="none"` the bar and line charts use.
  // Stretching turns a marker into a sliver on a narrow screen, and this chart
  // distinguishes its points by shape.
  const VIEW_W = 100
  const VIEW_H = 60
  const MARKER = 1.9

  // Padding leaves room for the axis labels, and enough margin that a marker
  // at an extreme value is not clipped by the viewBox edge.
  const padLeft = 6
  const padRight = 4
  const padTop = 4
  const padBottom = 10
  const plotW = VIEW_W - padLeft - padRight
  const plotH = VIEW_H - padTop - padBottom

  const xs = points.map((p) => p.x)
  const ys = points.map((p) => p.y)
  const xMin = Math.min(...xs)
  const xMax = Math.max(...xs)
  const yMin = Math.min(...ys)
  const yMax = Math.max(...ys)
  // A single point, or several sharing a value, would divide by zero; centre
  // them rather than pinning them to an edge.
  const xSpan = xMax - xMin || 1
  const ySpan = yMax - yMin || 1

  const px = (x: number) =>
    padLeft + (xMax === xMin ? 0.5 : (x - xMin) / xSpan) * plotW
  const py = (y: number) =>
    padTop + plotH - (yMax === yMin ? 0.5 : (y - yMin) / ySpan) * plotH

  const optimal = points.filter((p) => p.optimal)

  return (
    <figure className="chart">
      <svg
        viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
        role="img"
        aria-label={
          `Scatter of ${yLabel} against ${xLabel}. ` +
          `${optimal.length} of ${points.length} points are Pareto-optimal.`
        }
        style={{ width: '100%', height: 'auto', maxHeight: height }}
      >
        {points.map((point) =>
          point.optimal ? (
            // A diamond, not just a different colour: the distinction has to
            // survive for a reader who cannot separate the hues.
            <polygon
              key={point.run_id}
              points={
                `${px(point.x)},${py(point.y) - MARKER} ` +
                `${px(point.x) + MARKER},${py(point.y)} ` +
                `${px(point.x)},${py(point.y) + MARKER} ` +
                `${px(point.x) - MARKER},${py(point.y)}`
              }
              className="scatter-optimal"
            >
              <title>{`${point.label ?? point.run_id} — optimal`}</title>
            </polygon>
          ) : (
            <circle
              key={point.run_id}
              cx={px(point.x)}
              cy={py(point.y)}
              r={MARKER * 0.75}
              className="scatter-point"
            >
              <title>{point.label ?? point.run_id}</title>
            </circle>
          ),
        )}
        <text x={padLeft} y={VIEW_H - 2} className="chart-label">
          {xLabel} →
        </text>
        <text
          x={VIEW_W - padRight}
          y={VIEW_H - 2}
          textAnchor="end"
          className="chart-label"
        >
          {yHigherIsBetter ? '↑' : '↓'} {yLabel}
        </text>
      </svg>
      <figcaption className="muted">
        {optimal.length} of {points.length} measured point
        {points.length === 1 ? '' : 's'} sit on the frontier — not beaten on
        both axes at once. Diamonds are optimal.
      </figcaption>
    </figure>
  )
}
