import { describe, it, expect } from 'vitest'
import {
  matchingResults,
  recommendForQuiz,
  requirementsFor,
  type QuizAnswers,
} from '../src/lib/matchmaker'
import type { BenchmarkResultDoc, FitConstants } from '../src/lib/types'
import constantsJson from '../public/data/constants.json'

// The quiz's job is to say what it knows and refuse to say what it does not.
// These tests are mostly about the refusals: a recommender that answers
// confidently from nothing is worse than one that says the dataset is empty.

const constants = constantsJson as unknown as FitConstants

function answers(overrides: Partial<QuizAnswers> = {}): QuizAnswers {
  return {
    useCase: 'chat',
    priority: 'speed',
    hardware: 'small_gpu',
    ramGb: 16,
    ...overrides,
  }
}

function result(
  run_id: string,
  metrics: Record<string, number | null>,
): BenchmarkResultDoc {
  return {
    schema_version: '2.0',
    run_id,
    timestamp: '2026-01-01T00:00:00Z',
    system: { gpu: 'Test GPU', gpu_vram_mb: 8192 },
    runtime: { name: 'ollama', device: 'cuda' },
    model: { name: 'test-model' },
    metrics,
  } as unknown as BenchmarkResultDoc
}

describe('requirements', () => {
  it('derives a latency ceiling only where latency is the point', () => {
    // A summarization job is judged by finishing, not by starting quickly.
    expect(requirementsFor(answers({ useCase: 'long_documents' })).ttftCeilingMs).toBeNull()
    expect(requirementsFor(answers({ useCase: 'coding' })).ttftCeilingMs).not.toBeNull()
  })

  it('asks for more context when the task holds more', () => {
    const chat = requirementsFor(answers({ useCase: 'chat' })).contextLength
    const docs = requirementsFor(answers({ useCase: 'long_documents' })).contextLength
    expect(docs).toBeGreaterThan(chat)
  })

  it('trades speed against quality in the direction claimed', () => {
    const fast = requirementsFor(answers({ priority: 'speed' })).throughputFloorTps
    const good = requirementsFor(answers({ priority: 'quality' })).throughputFloorTps
    expect(fast).not.toBeNull()
    expect(good).not.toBeNull()
    expect(fast!).toBeGreaterThan(good!)
  })

  it('states every threshold it applied', () => {
    // The numbers are judgements, not measurements, so a reader has to be
    // able to see and disagree with them.
    const requirements = requirementsFor(answers({ useCase: 'agents' }))
    expect(requirements.notes.length).toBeGreaterThan(0)
    expect(requirements.notes.join(' ')).toContain('25 tok/s')
  })
})

describe('matching published results', () => {
  it('excludes a result missing the metric a requirement tests', () => {
    // "Not measured" is not evidence of clearing a threshold. Treating a null
    // as a pass is how a recommendation ends up resting on nothing.
    const requirements = requirementsFor(answers({ useCase: 'chat', priority: 'speed' }))
    const matches = matchingResults(requirements, [
      result('missing-tps', { ttft_ms: 100 }),
      result('has-both', { generation_tokens_per_second: 200, ttft_ms: 100 }),
    ])
    expect(matches.map((m) => m.run_id)).toEqual(['has-both'])
  })

  it('excludes a result that misses the throughput floor', () => {
    const requirements = requirementsFor(answers({ useCase: 'chat', priority: 'speed' }))
    const matches = matchingResults(requirements, [
      result('slow', { generation_tokens_per_second: 3, ttft_ms: 100 }),
    ])
    expect(matches).toEqual([])
  })

  it('excludes a result that exceeds the latency ceiling', () => {
    const requirements = requirementsFor(answers({ useCase: 'coding' }))
    const matches = matchingResults(requirements, [
      result('laggy', { generation_tokens_per_second: 500, ttft_ms: 5000 }),
    ])
    expect(matches).toEqual([])
  })

  it('orders by power, not speed, when the answer was battery life', () => {
    // Both still have to clear the task's own thresholds; battery decides the
    // ordering among what qualifies, not whether the task is usable at all.
    const requirements = requirementsFor(answers({ priority: 'battery' }))
    const matches = matchingResults(requirements, [
      result('thirsty', {
        generation_tokens_per_second: 300,
        ttft_ms: 200,
        average_power_watts: 90,
      }),
      result('frugal', {
        generation_tokens_per_second: 100,
        ttft_ms: 200,
        average_power_watts: 20,
      }),
    ])
    expect(matches.map((m) => m.run_id)).toEqual(['frugal', 'thirsty'])
  })

  it('excludes results with no power measurement when on battery', () => {
    const requirements = requirementsFor(answers({ priority: 'battery' }))
    const matches = matchingResults(requirements, [
      result('unmeasured', { generation_tokens_per_second: 300, ttft_ms: 200 }),
    ])
    expect(matches).toEqual([])
  })

  it('says why each result matched', () => {
    const requirements = requirementsFor(answers({ useCase: 'chat', priority: 'speed' }))
    const [match] = matchingResults(requirements, [
      result('fast', { generation_tokens_per_second: 250, ttft_ms: 300 }),
    ])
    expect(match!.reasons.join(' ')).toContain('tok/s')
    expect(match!.reasons.join(' ')).toContain('first token')
  })
})

describe('the recommendation', () => {
  it('reports measured evidence when a published result qualifies', () => {
    const out = recommendForQuiz(answers(), constants, [
      result('good', { generation_tokens_per_second: 250, ttft_ms: 300 }),
    ])
    expect(out.evidence).toBe('measured')
    expect(out.matches).toHaveLength(1)
    expect(out.headline).toContain('test-model')
  })

  it('falls back to an estimate, labelled as one, when nothing qualifies', () => {
    const out = recommendForQuiz(answers(), constants, [])
    expect(out.evidence).toBe('estimated')
    expect(out.matches).toEqual([])
    expect(out.detail).toContain('estimate')
    expect(out.sizeCeiling?.estimated_total_gb).not.toBeNull()
  })

  it('never claims a model is better at a task', () => {
    // This project measures speed, memory and power. It does not measure
    // whether one model writes better code than another, and the quiz must
    // not imply that it does.
    const out = recommendForQuiz(answers({ useCase: 'coding' }), constants, [
      result('good', { generation_tokens_per_second: 250, ttft_ms: 300 }),
    ])
    const prose = `${out.headline} ${out.detail}`.toLowerCase()
    for (const claim of ['best for', 'better at', 'smartest', 'most capable']) {
      expect(prose).not.toContain(claim)
    }
  })

  it('says the answer is measured but not necessarily on your hardware', () => {
    const out = recommendForQuiz(answers(), constants, [
      result('good', { generation_tokens_per_second: 250, ttft_ms: 300 }),
    ])
    expect(out.detail).toContain('not necessarily on hardware like yours')
  })

  it('carries the requirements it applied into the result', () => {
    const out = recommendForQuiz(answers({ useCase: 'agents' }), constants, [])
    expect(out.requirements.contextLength).toBe(16384)
    expect(out.requirements.notes.length).toBeGreaterThan(0)
  })
})
