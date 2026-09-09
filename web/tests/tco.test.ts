import { describe, it, expect } from 'vitest'
import { compareLocalVsCloud } from '../src/lib/tco'
import generated from '../public/data/tco.json'

// The canonical implementation is `compare_local_vs_cloud` in
// aihwbench/analysis/cost.py. The site must reach the same conclusion as the
// CLI about whether to buy hardware, so the reference cases it generates are
// replayed here. A divergence fails the build rather than telling a reader to
// spend money on the wrong thing.

interface Case {
  tokens_per_month: number | null
  cloud_usd_per_million_tokens: number | null
  hardware_cost_usd: number | null
  electricity_usd_per_kwh: number | null
  average_power_watts: number | null
  generation_tokens_per_second: number | null
  years: number
  expected: Record<string, unknown>
}

const CASES = (generated as unknown as { reference_cases: Case[] }).reference_cases

describe('compareLocalVsCloud parity with the Python implementation', () => {
  it('has reference cases to check against', () => {
    expect(CASES.length).toBeGreaterThan(0)
  })

  for (const [i, testCase] of CASES.entries()) {
    it(`matches case ${i + 1}: ${testCase.tokens_per_month} tokens/month`, () => {
      const actual = compareLocalVsCloud({
        tokensPerMonth: testCase.tokens_per_month,
        cloudUsdPerMillionTokens: testCase.cloud_usd_per_million_tokens,
        hardwareCostUsd: testCase.hardware_cost_usd,
        electricityUsdPerKwh: testCase.electricity_usd_per_kwh,
        averagePowerWatts: testCase.average_power_watts,
        generationTokensPerSecond: testCase.generation_tokens_per_second,
        years: testCase.years,
      })
      for (const key of [
        'cloud_cost_usd',
        'local_cost_usd',
        'local_energy_usd',
        'savings_usd',
        'break_even_months',
        'cheaper',
      ] as const) {
        expect(actual[key], key).toEqual(testCase.expected[key])
      }
    })
  }
})

describe('compareLocalVsCloud honesty properties', () => {
  const base = {
    tokensPerMonth: 10_000_000,
    cloudUsdPerMillionTokens: 10,
    hardwareCostUsd: 1200,
    electricityUsdPerKwh: 0,
    averagePowerWatts: 0,
    generationTokensPerSecond: 100,
    years: 3,
  }

  it('can conclude that the cloud is cheaper', () => {
    const report = compareLocalVsCloud({
      ...base,
      tokensPerMonth: 20_000_000,
      cloudUsdPerMillionTokens: 0.6,
      hardwareCostUsd: 1800,
      electricityUsdPerKwh: 0.3,
      averagePowerWatts: 180,
      generationTokensPerSecond: 45,
    })
    expect(report.cheaper).toBe('cloud')
    expect(report.savings_usd).toBeLessThan(0)
  })

  it('says never rather than a huge break-even figure', () => {
    const report = compareLocalVsCloud({
      ...base,
      tokensPerMonth: 1000,
      cloudUsdPerMillionTokens: 0.01,
      hardwareCostUsd: 2000,
      electricityUsdPerKwh: 0.4,
      averagePowerWatts: 300,
      generationTokensPerSecond: 40,
    })
    expect(report.break_even_months).toBeNull()
    expect(report.reason).toContain('never pays for itself')
  })

  it('reports missing inputs rather than defaulting them', () => {
    expect(compareLocalVsCloud({ ...base, tokensPerMonth: null }).reason).toContain(
      'monthly token volume is required',
    )
    expect(
      compareLocalVsCloud({ ...base, cloudUsdPerMillionTokens: null }).reason,
    ).toContain('cloud price per million tokens is required')
  })
})
