import { describe, expect, it } from 'vitest'
import {
  assertDataset,
  validateDataset,
  validateHardwareEntry,
  validateIndex,
  validateLeaderboardRow,
  validateMetrics,
  validateResultDoc,
  validateTrendPoint,
} from '../src/lib/validate'
import type { Dataset, Metrics } from '../src/lib/types'

function makeDataset(): Dataset {
  return {
    index: {
      schema_version: '1.0',
      results_count: 1,
      hardware_count: 1,
      runtime_count: 1,
      model_count: 1,
      source_dir: 'results/published',
      note: 'generated',
    },
    results: [
      {
        schema_version: '1.0',
        run_id: 'r1',
        timestamp: '2026-01-01T00:00:00Z',
        trust_state: 'verified',
        system: { cpu: 'X', cpu_cores_logical: 8 },
        runtime: { name: 'test' },
        model: { name: 'm' },
        metrics: { ttft_ms: 12.5, p95_latency_ms: null },
      },
    ],
    hardware: [{ fingerprint: 'abc123', ram_gb: 16, result_ids: ['r1'] }],
    runtimes: [{ name: 'test', versions: ['1.0'], device_options: ['cpu'], result_ids: ['r1'] }],
    models: [{ name: 'm', format: 'gguf', quantizations: [], checksums: [], result_ids: ['r1'] }],
    leaderboard: { throughput: [{ rank: 1, run_id: 'r1', value: 10.0 }], ttft: [], perf_watt: [] },
    trends: { test: [{ timestamp: '2026-01-01T00:00:00Z', version: '1.0', throughput: 10.0, ttft_ms: null }] },
  }
}

describe('validateIndex', () => {
  it('accepts a valid index', () => {
    expect(validateIndex(makeDataset().index)).toEqual([])
  })

  it('flags a missing schema_version', () => {
    const bad = { ...makeDataset().index }
    delete (bad as { schema_version?: string }).schema_version
    expect(validateIndex(bad)).not.toEqual([])
  })
})

describe('validateHardwareEntry', () => {
  it('flags a missing fingerprint', () => {
    expect(validateHardwareEntry({ result_ids: ['r1'] })).not.toEqual([])
  })

  it('accepts a valid entry with null ram_gb', () => {
    expect(validateHardwareEntry({ fingerprint: 'x', ram_gb: null, result_ids: [] })).toEqual([])
  })
})

describe('validateMetrics', () => {
  it('accepts numbers and null (not measured is null, never estimate)', () => {
    expect(validateMetrics({ ttft_ms: 12.5, p95_latency_ms: null, load_time_ms: null })).toEqual([])
  })

  it('rejects a string metric and NaN', () => {
    expect(validateMetrics({ ttft_ms: '12.5' })).not.toEqual([])
    expect(validateMetrics({ ttft_ms: NaN })).not.toEqual([])
  })
})

describe('validateResultDoc', () => {
  it('accepts a valid doc', () => {
    expect(validateResultDoc(makeDataset().results[0])).toEqual([])
  })

  it('flags missing run_id and timestamp', () => {
    const bad = { ...makeDataset().results[0], run_id: undefined, timestamp: undefined }
    const issues = validateResultDoc(bad)
    expect(issues.some((m) => m.includes('run_id'))).toBe(true)
    expect(issues.some((m) => m.includes('timestamp'))).toBe(true)
  })

  it('flags a corrupt iteration metric', () => {
    const bad = {
      ...makeDataset().results[0],
      iterations: [{ completion_tokens: 'five', eval_seconds: 0.1 }],
    }
    expect(validateResultDoc(bad)).not.toEqual([])
  })
})

describe('validateLeaderboardRow', () => {
  it('rejects a string value', () => {
    expect(validateLeaderboardRow({ rank: 1, run_id: 'r1', value: 'fast' })).not.toEqual([])
  })

  it('accepts a valid row with null value', () => {
    expect(validateLeaderboardRow({ rank: 1, run_id: 'r1', value: null })).toEqual([])
  })
})

describe('validateTrendPoint', () => {
  it('accepts null throughput (honest absence)', () => {
    expect(validateTrendPoint({ timestamp: '2026-01-01T00:00:00Z', throughput: null, ttft_ms: null })).toEqual([])
  })

  it('rejects string throughput', () => {
    expect(validateTrendPoint({ timestamp: '2026-01-01T00:00:00Z', throughput: 'fast' })).not.toEqual([])
  })
})

describe('validateDataset / assertDataset', () => {
  it('accepts the full valid dataset', () => {
    expect(validateDataset(makeDataset())).toEqual([])
  })

  it('fails closed on a corrupted metric', () => {
    const bad = makeDataset()
    bad.results[0]!.metrics = { ttft_ms: '12.5' } as unknown as Metrics
    const issues = validateDataset(bad)
    expect(issues.some((m) => m.includes('metrics.ttft_ms'))).toBe(true)
    expect(() => assertDataset(bad)).toThrow(/runtime contract validation/)
  })

  it('does not throw on a valid dataset', () => {
    expect(() => assertDataset(makeDataset())).not.toThrow()
  })
})