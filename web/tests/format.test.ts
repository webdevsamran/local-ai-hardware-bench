import { describe, expect, it } from 'vitest'
import { fmtDate, fmtInt, fmtNum, fmtPrecise, shortId, slugify, sortRows } from '../src/lib/format'

describe('fmtNum', () => {
  it('renders null/undefined/NaN as em dash', () => {
    expect(fmtNum(null)).toBe('—')
    expect(fmtNum(undefined)).toBe('—')
    expect(fmtNum(Number.NaN)).toBe('—')
  })

  it('formats numbers with digits', () => {
    expect(fmtNum(360.87, 1)).toBe('360.9')
    expect(fmtNum(0, 1)).toBe('0.0')
  })
})

describe('fmtInt', () => {
  it('renders missing as em dash and thousands separators', () => {
    expect(fmtInt(null)).toBe('—')
    expect(fmtInt(1234567)).toBe('1,234,567')
  })
})

describe('fmtDate', () => {
  it('slices ISO timestamps', () => {
    expect(fmtDate('2026-08-22T09:45:45Z')).toBe('2026-08-22')
  })
  it('passes through unparseable values', () => {
    expect(fmtDate('not-a-date')).toBe('not-a-date')
  })
})

describe('shortId / slugify', () => {
  it('truncates long ids', () => {
    expect(shortId('x'.repeat(30))).toHaveLength(25)
    expect(shortId('short-id')).toBe('short-id')
  })
  it('slugifies model names', () => {
    expect(slugify('Qwen2.5 0.5B Instruct (Q4_K_M)')).toBe(
      'qwen2-5-0-5b-instruct-q4_k_m',
    )
  })
})

describe('sortRows', () => {
  const rows = [
    { name: 'b', value: 2 },
    { name: 'a', value: 10 },
    { name: 'c', value: null },
  ]
  it('sorts numbers ascending with nulls last', () => {
    const sorted = sortRows(rows as never[], 'value', 'asc')
    expect(sorted.map((r: { name: string }) => r.name)).toEqual(['b', 'a', 'c'])
  })
  it('sorts numbers descending with nulls last', () => {
    const sorted = sortRows(rows as never[], 'value', 'desc')
    expect(sorted.map((r: { name: string }) => r.name)).toEqual(['a', 'b', 'c'])
  })
  it('sorts strings case-insensitively', () => {
    const sorted = sortRows(rows as never[], 'name', 'asc')
    expect(sorted.map((r: { name: string }) => r.name)).toEqual(['a', 'b', 'c'])
  })
})
// --- Precision that matches magnitude ---------------------------------------
//
// `fmtNum` fixes one decimal place, which is right for 297.1 tok/s and wrong
// for 0.0703 J/token — rendered as "0.1", a figure that has lost the
// information it existed to convey. Small measured quantities are common in
// this dataset: joules per token, coefficients of variation, fractions of
// gross power.

describe('fmtPrecise', () => {
  it('keeps a small measured value legible', () => {
    // The published per-token energy, which fmtNum rendered as "0.1".
    expect(fmtPrecise(0.0703)).toBe('0.0703')
  })

  it('keeps three significant figures below a hundredth', () => {
    // The figure that exposed the energy clamp: 0.00092 J/token.
    expect(fmtPrecise(0.00091978)).toBe('0.00092')
  })

  it('does not over-report a large value', () => {
    expect(fmtPrecise(297.05)).toBe('297')
    expect(fmtPrecise(29.5)).toBe('29.5')
  })

  it('trims trailing zeros', () => {
    expect(fmtPrecise(5)).toBe('5')
    expect(fmtPrecise(0.5)).toBe('0.5')
  })

  it('handles zero and missing values', () => {
    expect(fmtPrecise(0)).toBe('0')
    expect(fmtPrecise(null)).toBe('—')
    expect(fmtPrecise(undefined)).toBe('—')
    expect(fmtPrecise(Number.NaN)).toBe('—')
  })

  it('keeps the sign', () => {
    expect(fmtPrecise(-0.0703)).toBe('-0.0703')
  })
})
