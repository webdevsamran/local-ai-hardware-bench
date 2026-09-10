// Formatting helpers. Missing data renders as an em dash — never a
// fabricated zero.

export function fmtNum(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return value.toLocaleString('en-US', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
}

/**
 * Format a number at a precision its magnitude can carry.
 *
 * `fmtNum` fixes one decimal place, which is right for a throughput of 297.1
 * and wrong for a per-token energy of 0.0703 — rendered as "0.1", a figure
 * that has lost the information it existed to convey. Small measured
 * quantities are common here: joules per token, coefficients of variation,
 * fractions of gross power.
 *
 * Trailing zeros are trimmed, so 5 renders as "5" rather than "5.0000".
 */
export function fmtPrecise(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  const magnitude = Math.abs(value)
  let digits: number
  if (magnitude === 0) digits = 0
  else if (magnitude >= 100) digits = 0
  else if (magnitude >= 10) digits = 1
  else if (magnitude >= 1) digits = 2
  else if (magnitude >= 0.01) digits = 4
  // Below 0.01, keep three significant figures rather than a fixed place,
  // so 0.00091 does not become "0.0009".
  else digits = Math.min(20, 2 - Math.floor(Math.log10(magnitude)))

  return value
    .toLocaleString('en-US', { maximumFractionDigits: digits })
}

export function fmtInt(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return value.toLocaleString('en-US')
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toISOString().slice(0, 10)
}

export function shortId(id: string): string {
  return id.length > 24 ? id.slice(0, 24) + '…' : id
}

export function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9_]+/g, '-')
    .replace(/(^-|-$)/g, '')
}

export interface SortState<T> {
  key: keyof T & string
  dir: 'asc' | 'desc'
}

export function sortRows<T extends Record<string, unknown>>(
  rows: T[],
  key: keyof T & string,
  dir: 'asc' | 'desc',
): T[] {
  const sorted = [...rows].sort((a, b) => {
    const av = a[key]
    const bv = b[key]
    if (av === bv) return 0
    // Nulls always sort last regardless of direction.
    if (av === null || av === undefined) return 1
    if (bv === null || bv === undefined) return -1
    if (typeof av === 'number' && typeof bv === 'number') {
      return dir === 'asc' ? av - bv : bv - av
    }
    const as = String(av).toLowerCase()
    const bs = String(bv).toLowerCase()
    return dir === 'asc' ? as.localeCompare(bs) : bs.localeCompare(as)
  })
  return sorted
}