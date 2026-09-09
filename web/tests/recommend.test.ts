import { describe, it, expect } from 'vitest'
import { recommendConfiguration } from '../src/lib/recommend'
import type { BenchmarkResultDoc, FitConstants } from '../src/lib/types'
import constantsJson from '../public/data/constants.json'
import recommendJson from '../public/data/recommend.json'
import resultsJson from '../public/data/results.json'

// The site must advise the same configuration as `aihwbench recommend` for a
// given machine. Reference recommendations are computed by the canonical
// Python engine and replayed here; a divergence fails the build rather than
// telling someone to buy the wrong thing.

const constants = constantsJson as unknown as FitConstants
const results = resultsJson as unknown as BenchmarkResultDoc[]

interface Case {
  gpu_vram_mb: number | null
  ram_gb: number | null
  expected: {
    evidence_tier: string
    recommended_model_parameters_b: number | null
    recommended_runtime: string | null
    recommended_context_length: number
  }
}

const CASES = (recommendJson as unknown as { reference_cases: Case[] }).reference_cases

describe('recommendConfiguration parity with the Python engine', () => {
  it('has reference cases to check against', () => {
    expect(CASES.length).toBeGreaterThan(0)
  })

  for (const [i, testCase] of CASES.entries()) {
    const label = `${testCase.gpu_vram_mb ?? 'no GPU'} MB VRAM`
    it(`matches case ${i + 1}: ${label}`, () => {
      const actual = recommendConfiguration(
        constants,
        testCase.gpu_vram_mb,
        testCase.ram_gb,
        results,
      )
      expect(actual.recommended_model_parameters_b).toBe(
        testCase.expected.recommended_model_parameters_b,
      )
      expect(actual.recommended_context_length).toBe(
        testCase.expected.recommended_context_length,
      )
      expect(actual.evidence_tier).toBe(testCase.expected.evidence_tier)
      expect(actual.recommended_runtime).toBe(testCase.expected.recommended_runtime)
    })
  }
})

describe('recommendConfiguration invariants', () => {
  it.each([24576, 16384, 12288, 8192, 6144])(
    'recommends a model that fits in %i MB of VRAM',
    (vram) => {
      // The Python engine used to recommend a size its own fit check then
      // rejected. This holds the two in agreement on the browser side too.
      const out = recommendConfiguration(constants, vram, 32)
      expect(out.fit_check.fits).toBe(true)
      expect(out.fit_check.fit_target).toBe('vram')
    },
  )

  it('proposes no size when there is no memory figure at all', () => {
    const out = recommendConfiguration(constants, null, null)
    expect(out.recommended_model_parameters_b).toBeNull()
  })

  it('is an estimate until measured results anchor it', () => {
    const out = recommendConfiguration(constants, 8192, 16, [])
    expect(out.evidence_tier).toBe('estimated')
    expect(out.uncertainty).toContain('estimate')
  })

  it('upgrades to measured evidence when results exist', () => {
    const out = recommendConfiguration(constants, 8192, 16, results)
    expect(out.evidence_tier).toBe('measured')
    expect(out.recommended_runtime).toBeTruthy()
  })

  it('states the quantization the size assumes', () => {
    const out = recommendConfiguration(constants, 8192, 16)
    expect(out.assumed_quantization).toBe('q4_k_m')
    expect(out.reasons.join(' ')).toContain('bits/weight')
  })

  it('drops to a shorter context on a small memory budget', () => {
    expect(recommendConfiguration(constants, 6144, 16).recommended_context_length).toBe(2048)
    expect(recommendConfiguration(constants, 24576, 64).recommended_context_length).toBe(4096)
  })
})
