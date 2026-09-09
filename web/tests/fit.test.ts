import { describe, it, expect } from 'vitest'
import { estimateModelFit, offloadFraction, parseParameterCount } from '../src/lib/fit'
import type { FitConstants } from '../src/lib/types'
// Imported as data, not read at runtime: the generated file is the contract,
// so a stale or missing constants.json fails the build rather than the suite.
import generated from '../public/data/constants.json'

// The canonical estimator is `aihwbench/analysis/fit.py`. The browser needs
// the same answer without a Python runtime, so the logic exists twice — which
// is exactly the situation where two implementations quietly diverge and the
// site starts telling people a model fits when the CLI says it does not.
//
// `scripts/generate_frontend_data.py` writes reference cases computed by the
// Python function into data/constants.json. These tests replay them through
// the TypeScript one. A change to either side that alters an answer fails here.

const constants = generated as unknown as FitConstants

describe('estimateModelFit parity with the Python estimator', () => {
  it('has reference cases to check against', () => {
    expect(constants.reference_cases.length).toBeGreaterThan(0)
  })

  for (const [i, testCase] of constants.reference_cases.entries()) {
    const label = `${testCase.parameters ?? 'no params'} / ${testCase.quantization}`
    it(`matches case ${i + 1}: ${label}`, () => {
      const actual = estimateModelFit(
        constants,
        testCase.parameters,
        testCase.quantization,
        testCase.available_vram_mb,
        testCase.available_ram_mb,
      )
      expect(actual.estimated_weights_gb).toBe(testCase.expected.estimated_weights_gb)
      expect(actual.estimated_total_gb).toBe(testCase.expected.estimated_total_gb)
      expect(actual.fits).toBe(testCase.expected.fits)
      if (testCase.expected.fit_target !== undefined) {
        expect(actual.fit_target).toBe(testCase.expected.fit_target)
      }
    })
  }
})

describe('estimateModelFit refuses to guess', () => {
  it('returns no verdict for an unknown quantization', () => {
    const out = estimateModelFit(constants, '7B', 'not-a-real-quant', 8192, 32000)
    expect(out.fits).toBeNull()
    expect(out.estimated_total_gb).toBeNull()
    expect(out.reason).toContain('refusing to guess')
  })

  it('returns no verdict without a parameter count', () => {
    const out = estimateModelFit(constants, null, 'q4_k_m', 8192, 32000)
    expect(out.fits).toBeNull()
    expect(out.reason).toContain('cannot estimate')
  })

  it('reports no verdict when no memory figure is supplied', () => {
    const out = estimateModelFit(constants, '7B', 'q4_k_m', null, null)
    expect(out.estimated_total_gb).toBeGreaterThan(0)
    expect(out.fits).toBeNull()
  })
})

describe('parseParameterCount', () => {
  it.each([
    ['7B', 7e9],
    ['1.5b', 1.5e9],
    ['350M', 350e6],
    ['0.5B', 0.5e9],
  ])('parses %s', (text, expected) => {
    expect(parseParameterCount(text)).toBe(expected)
  })

  it.each([null, undefined, '', 'unknown', 'large'])('rejects %s', (text) => {
    expect(parseParameterCount(text)).toBeNull()
  })
})

describe('offloadFraction', () => {
  it('is zero when the model fits entirely in VRAM', () => {
    expect(offloadFraction(4, 8192)).toBe(0)
  })

  it('reports the share that must spill to system RAM', () => {
    // 10 GB model, 8 GB VRAM -> a fifth lives outside the GPU.
    expect(offloadFraction(10, 8000)).toBe(0.2)
  })

  it('has no answer without both figures', () => {
    expect(offloadFraction(null, 8192)).toBeNull()
    expect(offloadFraction(10, null)).toBeNull()
  })
})
