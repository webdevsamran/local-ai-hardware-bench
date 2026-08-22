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