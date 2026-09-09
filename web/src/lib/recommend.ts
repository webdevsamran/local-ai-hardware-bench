// Browser-side configuration recommender.
//
// Mirrors `recommend_configuration` in `aihwbench/analysis/recommend.py`,
// which stays canonical. Reference recommendations computed by that function
// are replayed through this one in web/tests, so the site and the CLI cannot
// advise differently about the same machine.
//
// Every recommendation carries its evidence tier. A figure derived from a
// memory budget and an assumed quantization density is an estimate, and one
// anchored on this dataset's measurements is not — conflating them would be
// the same error the comparison-safety classifier exists to prevent.

import type { BenchmarkResultDoc, FitConstants } from './types'
import { estimateModelFit, type FitEstimate } from './fit'

/** The quantization the recommendation assumes; stated in the output. */
export const ASSUMED_QUANTIZATION = 'q4_k_m'

export interface Recommendation {
  evidence_tier: 'measured' | 'estimated'
  recommended_model_parameters_b: number | null
  recommended_runtime: string | null
  recommended_device: string
  recommended_context_length: number
  assumed_quantization: string
  reasons: string[]
  uncertainty: string
  fit_check: FitEstimate
}

function round(value: number, places: number): number {
  const factor = 10 ** places
  return Math.round(value * factor) / factor
}

export function recommendConfiguration(
  constants: FitConstants,
  vramMb: number | null,
  ramGb: number | null,
  measured: BenchmarkResultDoc[] = [],
): Recommendation {
  const reasons: string[] = []
  let evidenceTier: 'measured' | 'estimated' = 'estimated'

  // Prefer VRAM; fall back to a conservative share of system RAM, because a
  // desktop OS needs the rest of it.
  let budgetGb: number | null = null
  if (vramMb !== null && vramMb > 0) {
    budgetGb = (vramMb / 1000) * 0.9
    reasons.push(
      `GPU VRAM ${vramMb.toFixed(0)} MB -> ~${budgetGb.toFixed(1)} GB usable weights budget (90%)`,
    )
  } else if (ramGb !== null && ramGb > 0) {
    budgetGb = ramGb * 0.5
    reasons.push(`no discrete GPU VRAM data; using 50% of ${ramGb.toFixed(0)} GB RAM`)
  }

  // Anchor the runtime on the fastest thing actually measured, when there is
  // one. This is what separates a recommendation from a calculator.
  let bestRuntime: string | null = null
  let bestDevice: string | null = null
  let bestTps: number | null = null
  for (const result of measured) {
    const tps = result.metrics?.generation_tokens_per_second
    if (tps != null && (bestTps === null || tps > bestTps)) {
      bestTps = tps
      bestRuntime = result.runtime?.name ?? null
      bestDevice = result.runtime?.device ?? null
    }
  }
  if (bestRuntime) {
    evidenceTier = 'measured'
    reasons.push(
      `best measured throughput ${bestTps?.toFixed(1)} tok/s on runtime=${bestRuntime}`,
    )
  }

  // Weights get the budget minus the runtime overhead the fit estimator
  // reserves. Sizing against the whole budget makes the recommendation fail
  // the fit check below, which is a contradiction rather than an estimate.
  const bits = constants.bits_per_weight[ASSUMED_QUANTIZATION]
  let maxParamsB: number | null = null
  if (budgetGb !== null && bits !== undefined) {
    const weightsBudgetGb = budgetGb / constants.overhead_factor
    maxParamsB = round((weightsBudgetGb * 8) / bits, 1)
    reasons.push(
      `~${maxParamsB}B parameters at ${ASSUMED_QUANTIZATION} density (${bits} bits/weight), ` +
        `leaving ${constants.overhead_factor}x for KV cache and runtime overhead — an estimate`,
    )
  }

  let contextLength = 4096
  if (budgetGb !== null && budgetGb < 6.0) {
    contextLength = 2048
    reasons.push('small memory budget: conservative 2048-token context suggested')
  }

  return {
    evidence_tier: evidenceTier,
    recommended_model_parameters_b: maxParamsB,
    recommended_runtime: bestRuntime,
    recommended_device: bestDevice ?? (vramMb ? 'gpu' : 'cpu'),
    recommended_context_length: contextLength,
    assumed_quantization: ASSUMED_QUANTIZATION,
    reasons,
    uncertainty:
      evidenceTier === 'estimated'
        ? "model-size figure is an estimate from memory budget and assumed quantization density; run 'aihwbench benchmark' to replace it with measured evidence"
        : "runtime/device anchored on this machine's own measurements",
    fit_check: estimateModelFit(
      constants,
      `${maxParamsB ?? 0}B`,
      ASSUMED_QUANTIZATION,
      vramMb,
      ramGb !== null ? ramGb * 1000 : null,
    ),
  }
}
