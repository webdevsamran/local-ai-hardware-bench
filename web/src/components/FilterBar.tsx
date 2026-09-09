import { useMemo } from 'react'

export interface FilterSpec<T> {
  /** Stable key, also used in the URL query string. */
  key: string
  label: string
  /** Value this row contributes to the facet, or null to exclude it. */
  valueOf: (row: T) => string | null | undefined
}

interface Props<T> {
  rows: T[]
  specs: FilterSpec<T>[]
  selected: Record<string, string>
  onChange: (key: string, value: string) => void
  onReset: () => void
}

/**
 * Faceted filters built from the data actually present.
 *
 * Options come from the rows rather than a hardcoded list, so a filter can
 * never offer a value that matches nothing — and a facet with only one value
 * is hidden, because a control that cannot change the result is noise.
 */
export default function FilterBar<T>({
  rows,
  specs,
  selected,
  onChange,
  onReset,
}: Props<T>) {
  const facets = useMemo(
    () =>
      specs
        .map((spec) => {
          const values = new Set<string>()
          for (const row of rows) {
            const value = spec.valueOf(row)
            if (value) values.add(value)
          }
          return { spec, options: Array.from(values).sort() }
        })
        .filter((facet) => facet.options.length > 1),
    [rows, specs],
  )

  const active = Object.values(selected).filter(Boolean).length

  if (facets.length === 0) return null

  return (
    <div className="facets" role="group" aria-label="Filters">
      {facets.map(({ spec, options }) => (
        <label className="field facet" key={spec.key}>
          <span className="field-label">{spec.label}</span>
          <select
            value={selected[spec.key] ?? ''}
            onChange={(event) => onChange(spec.key, event.target.value)}
          >
            <option value="">All</option>
            {options.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>
      ))}
      {active > 0 && (
        <button type="button" className="btn secondary facet-reset" onClick={onReset}>
          Clear {active} filter{active === 1 ? '' : 's'}
        </button>
      )}
    </div>
  )
}
