// Browser-side model-fit estimator.
//
// This mirrors `aihwbench/analysis/fit.py`, which stays canonical. The
// bits-per-weight table and the overhead factor are not duplicated here: they
// are generated into `data/constants.json` from the Python module, and that
// file also carries reference vectors the tests check this implementation
// against, so the two cannot drift apart silently.
//
// Everything it produces is an ESTIMATE. A measured result for the same model
// on the same hardware always beats it, and the UI says so.

import type { FitConstants } from './types'

export interface FitEstimate {
  estimated_weights_gb: number | null
  estimated_total_gb: number | null
  fits: boolean | null
  fit_target: string | null
  reason: string
}

const PARAM_RE = /([\d.]+)\s*([bmk])\b/i
const MULTIPLIERS: Record<string, number> = { k: 1e3, m: 1e6, b: 1e9 }

/** Parse '7B', '1.5b', '350M' style parameter counts. */
export function parseParameterCount(text: string | null | undefined): number | null {
  if (!text) return null
  const match = PARAM_RE.exec(text)
  const value = match?.[1]
  const unit = match?.[2]
  if (value === undefined || unit === undefined) return null
  const multiplier = MULTIPLIERS[unit.toLowerCase()]
  if (multiplier === undefined) return null
  return parseFloat(value) * multiplier
}

function round(value: number, places: number): number {
  const factor = 10 ** places
  return Math.round(value * factor) / factor
}

/**
 * Estimate memory need against what the machine has.
 *
 * An unknown quantization returns `fits: null` with a reason rather than a
 * guess: inventing a bits-per-weight figure would produce a confident answer
 * from nothing, which is the failure this project exists to avoid.
 */
export function estimateModelFit(
  constants: FitConstants,
  parametersText: string | null | undefined,
  quantization: string | null | undefined,
  availableVramMb: number | null = null,
  availableRamMb: number | null = null,
): FitEstimate {
  const params = parseParameterCount(parametersText)
  if (params === null) {
    return {
      estimated_weights_gb: null,
      estimated_total_gb: null,
      fits: null,
      fit_target: null,
      reason: 'parameter count unavailable; cannot estimate',
    }
  }

  const bits = constants.bits_per_weight[(quantization ?? '').toLowerCase()]
  if (bits === undefined) {
    return {
      estimated_weights_gb: null,
      estimated_total_gb: null,
      fits: null,
      fit_target: null,
      reason: `unknown quantization '${quantization}'; refusing to guess bits-per-weight`,
    }
  }

  const weightsBytes = (params * bits) / 8.0
  const totalGb = (weightsBytes * constants.overhead_factor) / 1e9

  const candidates: [string, number][] = []
  if (availableVramMb !== null) candidates.push(['vram', availableVramMb / 1000.0])
  if (availableRamMb !== null) candidates.push(['ram', availableRamMb / 1000.0])

  let fits: boolean | null = null
  let target: string | null = null
  for (const [name, gb] of candidates) {
    if (gb >= totalGb) {
      fits = true
      target = name
      break
    }
    fits = false
    target = name
  }

  return {
    estimated_weights_gb: round(weightsBytes / 1e9, 3),
    estimated_total_gb: round(totalGb, 3),
    fits,
    fit_target: target,
    reason:
      candidates.length > 0
        ? `estimated ${totalGb.toFixed(2)} GB needed vs ` +
          candidates.map(([n, gb]) => `${n} ${gb.toFixed(1)} GB`).join(', ')
        : 'no memory availability supplied',
  }
}

/**
 * How much of the model has to live outside VRAM.
 *
 * The single biggest performance cliff in local inference is the moment a
 * model spills from GPU to system RAM, and the size of the spill is what
 * decides how far throughput falls. This reports the ratio; it deliberately
 * does not predict a speed, because that depends on the machine and is what
 * the measured dataset is for.
 */
export function offloadFraction(
  totalGb: number | null,
  availableVramMb: number | null,
): number | null {
  if (totalGb === null || availableVramMb === null || totalGb <= 0) return null
  const vramGb = availableVramMb / 1000.0
  if (vramGb >= totalGb) return 0
  return round((totalGb - vramGb) / totalGb, 3)
}
