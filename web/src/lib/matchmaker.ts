// "What should I run, for what I actually want to do?"
//
// The recommender at /recommend answers a hardware question: given this much
// memory, how big a model fits. This answers the question people ask first,
// which is about the task rather than the silicon -- and the two have
// different right answers. A model that fits is not the same as a model that
// responds fast enough to feel like a conversation.
//
// What this deliberately does not do
// ----------------------------------
// It does not claim to know which model is good at which task. This
// repository measures speed, memory, power and thermals; it does not measure
// whether one model writes better code than another, and a quiz that ranked
// models by task quality would be inventing knowledge the dataset does not
// contain. Saying "this model is best for coding" from a throughput dataset
// is exactly the kind of confident, unfounded claim the project exists to
// avoid.
//
// What it does instead is turn answers into *requirements* -- a memory
// budget, a context length, a latency ceiling, a power constraint -- and then
// look for published results that meet them. Where measured evidence exists
// it is used and labelled as measured. Where it does not, the fit estimator
// supplies a ceiling and the answer says it is an estimate. Where neither can
// help, it says so rather than guessing.

import type { BenchmarkResultDoc, FitConstants } from './types'
import { estimateModelFit, type FitEstimate } from './fit'

export type UseCase = 'chat' | 'coding' | 'long_documents' | 'agents'
export type Priority = 'speed' | 'quality' | 'battery'
export type HardwareTier = 'no_gpu' | 'small_gpu' | 'mid_gpu' | 'large_gpu'

export interface QuizAnswers {
  useCase: UseCase
  priority: Priority
  hardware: HardwareTier
  ramGb: number
}

/** What an answer set implies, before any model is considered. */
export interface Requirements {
  /** Tokens of context the task needs the model to hold. */
  contextLength: number
  /**
   * Time to first token, in ms, above which the task stops feeling right.
   * Null when the task is not latency-sensitive -- a long summarization job
   * is judged by whether it finishes, not by how fast it starts.
   */
  ttftCeilingMs: number | null
  /** Generation rate below which the task becomes painful, in tok/s. */
  throughputFloorTps: number | null
  /** VRAM available for weights, in MB. Null when there is no discrete GPU. */
  vramMb: number | null
  /** True when the machine is expected to be on battery. */
  powerConstrained: boolean
  notes: string[]
}

export interface Match {
  run_id: string
  model: string
  runtime: string
  device: string | null
  generation_tokens_per_second: number | null
  ttft_ms: number | null
  average_power_watts: number | null
  /** Why this result satisfied the requirements. */
  reasons: string[]
}

export interface Recommendation {
  requirements: Requirements
  /** Published results meeting every requirement, best first. */
  matches: Match[]
  /**
   * How the answer was reached. `measured` means at least one published
   * result satisfied the requirements; `estimated` means none did and the
   * size ceiling comes from the fit estimator; `insufficient_data` means
   * neither could answer.
   */
  evidence: 'measured' | 'estimated' | 'insufficient_data'
  /** Model-size ceiling from the memory budget, when one can be computed. */
  sizeCeiling: FitEstimate | null
  headline: string
  detail: string
}

/** VRAM each hardware tier stands in for, in MB. */
const TIER_VRAM: Record<HardwareTier, number | null> = {
  no_gpu: null,
  small_gpu: 8192,
  mid_gpu: 12288,
  large_gpu: 24576,
}

const TIER_LABEL: Record<HardwareTier, string> = {
  no_gpu: 'no discrete GPU',
  small_gpu: 'an 8 GB GPU',
  mid_gpu: 'a 12 GB GPU',
  large_gpu: 'a 24 GB GPU',
}

/**
 * The quantization the size ceiling assumes.
 *
 * Stated in the output rather than hidden, because the ceiling moves by a
 * factor of four between 4-bit and 16-bit and a number without its assumption
 * is not an estimate, it is a guess wearing one.
 */
export const ASSUMED_QUANTIZATION = 'q4_k_m'

/**
 * Turn answers into requirements.
 *
 * Every threshold here is a judgement, not a measurement, so each one is
 * stated in `notes` where the reader can disagree with it.
 */
export function requirementsFor(answers: QuizAnswers): Requirements {
  const notes: string[] = []
  const vramMb = TIER_VRAM[answers.hardware]

  let contextLength = 4096
  let ttftCeilingMs: number | null = null
  let throughputFloorTps: number | null = null

  switch (answers.useCase) {
    case 'chat':
      // Reading speed is roughly 5-8 tokens/second, so anything above about
      // 15 keeps text arriving faster than it can be read.
      throughputFloorTps = 15
      ttftCeilingMs = 1500
      notes.push(
        'Conversation is judged by whether text outruns reading: a floor of 15 tok/s and a first token inside 1.5 s.',
      )
      break
    case 'coding':
      // Completion suggestions are compared against the cost of just typing
      // it, so the first token has to arrive very fast.
      contextLength = 8192
      throughputFloorTps = 20
      ttftCeilingMs = 600
      notes.push(
        'Code completion competes with typing it yourself, so the first token matters more than the rate: 600 ms, and 8K of context to hold the surrounding file.',
      )
      break
    case 'long_documents':
      contextLength = 32768
      notes.push(
        'Long-document work needs 32K of context. No latency ceiling is applied: a summarization job is judged by finishing, not by starting quickly.',
      )
      break
    case 'agents':
      contextLength = 16384
      throughputFloorTps = 25
      notes.push(
        'An agent loop pays the generation cost once per step, so slow generation compounds: a floor of 25 tok/s and 16K of context for accumulated tool output.',
      )
      break
  }

  if (answers.priority === 'speed' && throughputFloorTps !== null) {
    throughputFloorTps = Math.round(throughputFloorTps * 1.5)
    notes.push('Speed chosen over quality: the throughput floor is raised by half.')
  }
  if (answers.priority === 'quality') {
    // A larger model at the same memory means fewer bits per weight or a
    // slower rate; either way the speed requirement has to give.
    throughputFloorTps = throughputFloorTps === null ? null : Math.round(throughputFloorTps * 0.6)
    notes.push(
      'Quality chosen over speed: the throughput floor is relaxed, since a larger model on the same memory is a slower one.',
    )
  }

  const powerConstrained = answers.priority === 'battery'
  if (powerConstrained) {
    notes.push(
      'On battery, sustained draw decides how long the machine lasts, so results are ordered by measured power rather than speed.',
    )
  }

  if (vramMb === null) {
    notes.push(
      `With ${TIER_LABEL[answers.hardware]}, weights live in system RAM and generation is bounded by memory bandwidth rather than compute.`,
    )
  }

  return {
    contextLength,
    ttftCeilingMs,
    throughputFloorTps,
    vramMb,
    powerConstrained,
    notes,
  }
}

function matchFor(result: BenchmarkResultDoc, reasons: string[]): Match {
  const metrics = result.metrics ?? {}
  return {
    run_id: result.run_id,
    model: result.model?.name ?? 'unknown',
    runtime: result.runtime?.name ?? 'unknown',
    device: result.runtime?.device ?? null,
    generation_tokens_per_second: metrics.generation_tokens_per_second ?? null,
    ttft_ms: metrics.ttft_ms ?? null,
    average_power_watts: metrics.average_power_watts ?? null,
    reasons,
  }
}

/**
 * Published results that meet the requirements.
 *
 * A result missing the metric a requirement tests is excluded rather than
 * assumed to pass. "We did not measure this" is not evidence of meeting a
 * threshold, and treating it as one is how a recommendation ends up resting
 * on nothing.
 */
export function matchingResults(
  requirements: Requirements,
  results: BenchmarkResultDoc[],
): Match[] {
  const matches: Match[] = []

  for (const result of results) {
    const metrics = result.metrics ?? {}
    const tps = metrics.generation_tokens_per_second
    const ttft = metrics.ttft_ms
    const reasons: string[] = []

    if (requirements.throughputFloorTps !== null) {
      if (tps == null || tps < requirements.throughputFloorTps) continue
      reasons.push(
        `${tps.toFixed(1)} tok/s clears the ${requirements.throughputFloorTps} tok/s floor`,
      )
    }
    if (requirements.ttftCeilingMs !== null) {
      if (ttft == null || ttft > requirements.ttftCeilingMs) continue
      reasons.push(`first token in ${ttft.toFixed(0)} ms`)
    }
    if (requirements.powerConstrained) {
      const watts = metrics.average_power_watts
      if (watts == null) continue
      reasons.push(`measured at ${watts.toFixed(1)} W`)
    }
    matches.push(matchFor(result, reasons))
  }

  // On battery the ordering question is power, not speed. Everywhere else it
  // is throughput. Results missing the sort key go last rather than being
  // treated as zero.
  matches.sort((a, b) => {
    if (requirements.powerConstrained) {
      const left = a.average_power_watts ?? Number.POSITIVE_INFINITY
      const right = b.average_power_watts ?? Number.POSITIVE_INFINITY
      return left - right
    }
    const left = a.generation_tokens_per_second ?? Number.NEGATIVE_INFINITY
    const right = b.generation_tokens_per_second ?? Number.NEGATIVE_INFINITY
    return right - left
  })

  return matches
}

/** The largest model the memory budget allows, as an estimate. */
function sizeCeilingFor(
  constants: FitConstants,
  requirements: Requirements,
  ramGb: number,
): FitEstimate | null {
  const bits = constants.bits_per_weight[ASSUMED_QUANTIZATION]
  if (bits === undefined) return null

  const budgetGb =
    requirements.vramMb !== null && requirements.vramMb > 0
      ? (requirements.vramMb / 1000) * 0.9
      : ramGb * 0.5
  const weightsBudgetGb = budgetGb / constants.overhead_factor
  const maxParamsB = Math.round(((weightsBudgetGb * 8) / bits) * 10) / 10

  return estimateModelFit(
    constants,
    `${maxParamsB}B`,
    ASSUMED_QUANTIZATION,
    requirements.vramMb,
    ramGb * 1000,
  )
}

export function recommendForQuiz(
  answers: QuizAnswers,
  constants: FitConstants,
  results: BenchmarkResultDoc[] = [],
): Recommendation {
  const requirements = requirementsFor(answers)
  const matches = matchingResults(requirements, results)
  const sizeCeiling = sizeCeilingFor(constants, requirements, answers.ramGb)

  if (matches.length > 0) {
    const best = matches[0]!
    return {
      requirements,
      matches,
      evidence: 'measured',
      sizeCeiling,
      headline: `${best.model} on ${best.runtime}`,
      detail:
        `${matches.length} published result${matches.length === 1 ? '' : 's'} ` +
        `met every requirement for this task. This is measured on real hardware, ` +
        `not estimated — though not necessarily on hardware like yours, which is ` +
        `what the comparison-safety rules exist to tell you.`,
    }
  }

  if (sizeCeiling && sizeCeiling.estimated_total_gb !== null) {
    return {
      requirements,
      matches,
      evidence: 'estimated',
      sizeCeiling,
      headline: 'No published result meets these requirements yet',
      detail:
        `Nothing in the dataset has been measured meeting this task's ` +
        `thresholds, so there is no measured answer to give. What can be said ` +
        `from your memory budget alone is a size ceiling, below — an estimate, ` +
        `and no substitute for a measurement.`,
    }
  }

  return {
    requirements,
    matches,
    evidence: 'insufficient_data',
    sizeCeiling,
    headline: 'Not enough information',
    detail:
      'Neither the dataset nor the memory budget can answer this. Contributing ' +
      'a result from your own hardware is what turns this into an answer.',
  }
}
