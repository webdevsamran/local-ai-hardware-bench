/**
 * Charts that show the shape of data rather than compare values.
 *
 * The rule they all share with the rest of the site: a chart never invents a
 * value. An unmeasured cell is not a cold one, four points are not a
 * distribution, and every picture has the numbers behind it for anyone who
 * cannot see the picture.
 */

import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { AreaChart, Heatmap, ViolinChart } from '../src/components/Distributions'

describe('AreaChart', () => {
  const data = [
    { label: 'iter 1', value: 10 },
    { label: 'iter 2', value: 20 },
    { label: 'iter 3', value: 30 },
  ]

  it('renders nothing for a single point', () => {
    // One point is not a trend, and an area drawn from it implies one.
    const { container } = render(<AreaChart data={[{ label: 'a', value: 1 }]} />)
    expect(container.firstChild).toBeNull()
  })

  it('plots running totals when asked to', () => {
    render(<AreaChart data={data} unit="J" cumulative />)
    // 10, 30, 60 — the last is the total, not the last value.
    expect(screen.getByText(/60.00/)).toBeTruthy()
    expect(screen.getByText(/running total/)).toBeTruthy()
  })

  it('plots the values themselves when not cumulative', () => {
    render(<AreaChart data={data} unit="J" />)
    expect(screen.getByText(/30.00/)).toBeTruthy()
  })

  it('puts the numbers behind the picture', () => {
    // A described image is not the data. Every chart carries a table.
    render(<AreaChart data={data} />)
    expect(screen.getByRole('table', { hidden: true })).toBeTruthy()
  })
})

describe('Heatmap', () => {
  const cells = [
    { row: 'K f16', column: 'V f16', value: 1022 },
    { row: 'K f16', column: 'V q4_0', value: 854 },
    { row: 'K q4_0', column: 'V f16', value: 1810 },
    { row: 'K q4_0', column: 'V q4_0', value: 748 },
  ]

  it('renders a cell per combination', () => {
    render(<Heatmap cells={cells} rowLabel="K" columnLabel="V" unit="MiB" />)
    expect(screen.getByText('1022')).toBeTruthy()
    expect(screen.getByText('1810')).toBeTruthy()
  })

  it('marks an unmeasured cell as absent rather than zero', () => {
    // A blank cell and a cold cell mean different things, and a heatmap that
    // shades a missing value the same as a minimum invents a measurement.
    render(
      <Heatmap
        cells={[...cells, { row: 'K q8_0', column: 'V q8_0', value: null }]}
        rowLabel="K"
        columnLabel="V"
      />,
    )
    // Adding one cell adds a row *and* a column, so the grid grows to 3x3 and
    // five of the nine combinations were never measured. All of them say so.
    const missing = screen.getAllByTitle('not measured')
    expect(missing).toHaveLength(5)
    for (const cell of missing) {
      expect(cell.textContent).toBe('—')
      expect(cell.className).toContain('heat-missing')
    }
  })

  it('carries the value as text so colour is never the only channel', () => {
    const { container } = render(<Heatmap cells={cells} rowLabel="K" columnLabel="V" />)
    for (const cell of container.querySelectorAll('.heat-cell')) {
      expect(cell.textContent?.trim()).toMatch(/\d/)
    }
  })

  it('inverts the scale when lower is better', () => {
    const { container } = render(
      <Heatmap cells={cells} rowLabel="K" columnLabel="V" lowerIsBetter />,
    )
    const heats = [...container.querySelectorAll('.heat-cell')].map((c) =>
      Number((c as HTMLElement).style.getPropertyValue('--heat')),
    )
    // 748 is the best figure when lower is better, so it is the darkest.
    expect(Math.max(...heats)).toBeCloseTo(1, 2)
    expect(screen.getByText(/Darker is lower/)).toBeTruthy()
  })

  it('renders nothing when no cell was measured', () => {
    const { container } = render(
      <Heatmap cells={[{ row: 'a', column: 'b', value: null }]} rowLabel="K" columnLabel="V" />,
    )
    expect(container.firstChild).toBeNull()
  })
})

describe('ViolinChart', () => {
  it('refuses a series too short to describe a distribution', () => {
    // Three points have a shape only in the sense that any three points do.
    const { container } = render(<ViolinChart series={[{ label: 'a', values: [1, 2, 3] }]} />)
    expect(container.firstChild).toBeNull()
  })

  it('draws a body and a median per series', () => {
    const { container } = render(
      <ViolinChart
        series={[
          { label: 'llama.cpp', values: [320, 330, 340, 180, 175, 170, 350, 345] },
          { label: 'ollama', values: [200, 205, 198, 202, 199, 201, 203, 197] },
        ]}
        unit="tok/s"
      />,
    )
    expect(container.querySelectorAll('.violin-body')).toHaveLength(2)
    expect(container.querySelectorAll('.violin-median')).toHaveLength(2)
  })

  it('explains what two lobes mean', () => {
    // The whole reason this chart exists: a bimodal machine's mean is a rate
    // it never sustained.
    render(<ViolinChart series={[{ label: 'a', values: [1, 2, 3, 4, 90, 91, 92, 93] }]} />)
    expect(screen.getByText(/never sustained/)).toBeTruthy()
  })

  it('summarises each distribution for a screen reader', () => {
    render(<ViolinChart series={[{ label: 'a', values: [1, 2, 3, 4] }]} unit="tok/s" />)
    expect(screen.getByText(/4 iterations, min 1.0/)).toBeTruthy()
  })
})
