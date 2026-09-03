// Zero-dependency runtime validation for the generated static dataset.
//
// The TS interfaces in types.ts are a compile-time contract only; this module
// checks the real fetched JSON at runtime so corruption or schema drift fails
// loudly with a readable message instead of silently rendering undefined
// fields. This is a *structural* contract (required fields, types, and the
// null-or-measured semantics), not a full re-implementation of the Python
// semantic validation in aihwbench/schemas.py.
//
// Honesty rule: metric fields accept `number | null` — never a string or an
// invented value. `null` means "not measured", and the checker preserves that
// distinction.

import type { Dataset } from './types'

/** A short, human-readable path prefix plus the problem. */
type Issue = string

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v)
}

function isNonEmptyString(v: unknown): boolean {
  return typeof v === 'string' && v.length > 0
}

function isFiniteNumber(v: unknown): boolean {
  return typeof v === 'number' && Number.isFinite(v)
}

function isNumberOrNull(v: unknown): boolean {
  return v === null || isFiniteNumber(v)
}

function isStringOrNull(v: unknown): boolean {
  return v === null || typeof v === 'string'
}

function isStringArray(v: unknown): v is string[] {
  return Array.isArray(v) && v.every((x) => typeof x === 'string')
}

function isResultIdArray(v: unknown): boolean {
  return Array.isArray(v) && v.every((x) => isNonEmptyString(x))
}

function metricNumber(path: string, v: unknown, issues: Issue[]): void {
  if (!isNumberOrNull(v)) issues.push(`${path}: expected number or null, got ${String(v)}`)
}

function optionalString(path: string, v: unknown, issues: Issue[]): void {
  if (v !== undefined && !isStringOrNull(v)) {
    issues.push(`${path}: expected string or null, got ${String(v)}`)
  }
}

export function validateIndex(d: unknown): Issue[] {
  const issues: Issue[] = []
  if (!isRecord(d)) return [`index: expected object, got ${String(d)}`]
  for (const key of ['schema_version', 'source_dir'] as const) {
    if (!isNonEmptyString(d[key])) issues.push(`index.${key}: expected non-empty string`)
  }
  for (const key of ['results_count', 'hardware_count', 'runtime_count', 'model_count'] as const) {
    if (typeof d[key] !== 'number') issues.push(`index.${key}: expected number`)
  }
  return issues
}

export function validateHardwareEntry(d: unknown): Issue[] {
  const issues: Issue[] = []
  if (!isRecord(d)) return [`hardware[]: expected object, got ${String(d)}`]
  if (!isNonEmptyString(d.fingerprint)) issues.push('hardware[].fingerprint: expected non-empty string')
  if (d.ram_gb !== undefined && !isNumberOrNull(d.ram_gb)) issues.push('hardware[].ram_gb: expected number or null')
  if (!isResultIdArray(d.result_ids)) issues.push('hardware[].result_ids: expected array of non-empty strings')
  return issues
}

export function validateRuntimeEntry(d: unknown): Issue[] {
  const issues: Issue[] = []
  if (!isRecord(d)) return [`runtimes[]: expected object, got ${String(d)}`]
  if (!isNonEmptyString(d.name)) issues.push('runtimes[].name: expected non-empty string')
  if (!isStringArray(d.versions)) issues.push('runtimes[].versions: expected array of strings')
  if (!isStringArray(d.device_options)) issues.push('runtimes[].device_options: expected array of strings')
  if (!isResultIdArray(d.result_ids)) issues.push('runtimes[].result_ids: expected array of non-empty strings')
  return issues
}

export function validateModelEntry(d: unknown): Issue[] {
  const issues: Issue[] = []
  if (!isRecord(d)) return [`models[]: expected object, got ${String(d)}`]
  if (!isNonEmptyString(d.name)) issues.push('models[].name: expected non-empty string')
  optionalString('models[].format', d.format, issues)
  if (!isStringArray(d.quantizations)) issues.push('models[].quantizations: expected array of strings')
  if (!isStringArray(d.checksums)) issues.push('models[].checksums: expected array of strings')
  if (!isResultIdArray(d.result_ids)) issues.push('models[].result_ids: expected array of non-empty strings')
  return issues
}

const METRIC_KEYS = [
  'load_time_ms',
  'ttft_ms',
  'prompt_tokens_per_second',
  'generation_tokens_per_second',
  'total_latency_ms',
  'p50_latency_ms',
  'p95_latency_ms',
  'p99_latency_ms',
  'peak_ram_mb',
  'peak_vram_mb',
  'avg_cpu_util_percent',
  'avg_gpu_util_percent',
  'max_temperature_c',
  'average_power_watts',
  'performance_per_watt',
] as const

export function validateMetrics(d: unknown): Issue[] {
  const issues: Issue[] = []
  if (!isRecord(d)) return [`metrics: expected object, got ${String(d)}`]
  for (const key of METRIC_KEYS) {
    if (d[key] !== undefined) metricNumber(`metrics.${key}`, d[key], issues)
  }
  return issues
}

export function validateIteration(d: unknown): Issue[] {
  const issues: Issue[] = []
  if (!isRecord(d)) return [`iterations[]: expected object, got ${String(d)}`]
  for (const key of ['completion_tokens', 'prompt_tokens'] as const) {
    if (d[key] !== undefined && !isNumberOrNull(d[key])) {
      issues.push(`iterations[].${key}: expected number or null`)
    }
  }
  for (const key of ['eval_seconds', 'prompt_eval_seconds', 'total_latency_ms', 'ttft_ms'] as const) {
    if (d[key] !== undefined) metricNumber(`iterations[].${key}`, d[key], issues)
  }
  return issues
}

export function validateResultDoc(d: unknown): Issue[] {
  const issues: Issue[] = []
  if (!isRecord(d)) return [`results[]: expected object, got ${String(d)}`]
  if (!isNonEmptyString(d.schema_version)) issues.push('results[].schema_version: expected non-empty string')
  if (!isNonEmptyString(d.run_id)) issues.push('results[].run_id: expected non-empty string')
  if (!isNonEmptyString(d.timestamp)) issues.push('results[].timestamp: expected non-empty string')
  optionalString('results[].trust_state', d.trust_state, issues)
  if (d.system !== undefined && !isRecord(d.system)) issues.push('results[].system: expected object')
  if (d.runtime !== undefined && !isRecord(d.runtime)) issues.push('results[].runtime: expected object')
  if (d.model !== undefined && !isRecord(d.model)) issues.push('results[].model: expected object')
  if (d.metrics !== undefined) issues.push(...validateMetrics(d.metrics))
  if (d.iterations !== undefined) {
    if (!Array.isArray(d.iterations)) {
      issues.push('results[].iterations: expected array')
    } else {
      for (let i = 0; i < d.iterations.length; i++) {
        issues.push(...validateIteration(d.iterations[i]).map((m) => `results[].iterations[${i}].${m}`))
      }
    }
  }
  return issues
}

export function validateLeaderboardRow(d: unknown): Issue[] {
  const issues: Issue[] = []
  if (!isRecord(d)) return [`leaderboard rows: expected object, got ${String(d)}`]
  if (typeof d.rank !== 'number') issues.push('leaderboard[].rank: expected number')
  if (!isNonEmptyString(d.run_id)) issues.push('leaderboard[].run_id: expected non-empty string')
  optionalString('leaderboard[].model', d.model, issues)
  optionalString('leaderboard[].runtime', d.runtime, issues)
  optionalString('leaderboard[].cpu', d.cpu, issues)
  optionalString('leaderboard[].gpu', d.gpu, issues)
  metricNumber('leaderboard[].value', d.value, issues)
  return issues
}

export function validateLeaderboardViews(d: unknown): Issue[] {
  const issues: Issue[] = []
  if (!isRecord(d)) return [`leaderboard: expected object, got ${String(d)}`]
  for (const view of ['throughput', 'ttft', 'perf_watt'] as const) {
    if (d[view] === undefined) continue
    if (!Array.isArray(d[view])) {
      issues.push(`leaderboard.${view}: expected array`)
    } else {
      issues.push(...d[view].flatMap(validateLeaderboardRow).map((m) => `leaderboard.${view}: ${m}`))
    }
  }
  return issues
}

export function validateTrendPoint(d: unknown): Issue[] {
  const issues: Issue[] = []
  if (!isRecord(d)) return [`trends: expected object, got ${String(d)}`]
  metricNumber('trends[].throughput', d.throughput, issues)
  metricNumber('trends[].ttft_ms', d.ttft_ms, issues)
  if (d.timestamp !== undefined && !isNonEmptyString(d.timestamp)) issues.push('trends[].timestamp: expected string')
  optionalString('trends[].version', d.version, issues)
  return issues
}

export function validateTrends(d: unknown): Issue[] {
  const issues: Issue[] = []
  if (!isRecord(d)) return [`trends: expected object, got ${String(d)}`]
  for (const [runtime, points] of Object.entries(d)) {
    if (!Array.isArray(points)) {
      issues.push(`trends.${runtime}: expected array`)
      continue
    }
    issues.push(...points.flatMap(validateTrendPoint))
  }
  return issues
}

/**
 * Validate the whole dataset contract. Returns an empty array when valid.
 * Tolerant of absent optional blocks; strict about types and the
 * null-or-measured metric semantics.
 */
export function validateDataset(d: unknown): Issue[] {
  if (!isRecord(d)) return [`dataset: expected object, got ${String(d)}`]
  const issues: Issue[] = []
  const results = (d.results as unknown[] | undefined) ?? []
  const hardware = (d.hardware as unknown[] | undefined) ?? []
  const runtimes = (d.runtimes as unknown[] | undefined) ?? []
  const models = (d.models as unknown[] | undefined) ?? []
  issues.push(...validateIndex(d.index))
  if (!Array.isArray(results)) return [...issues, 'results: expected array']
  if (!Array.isArray(hardware)) return [...issues, 'hardware: expected array']
  if (!Array.isArray(runtimes)) return [...issues, 'runtimes: expected array']
  if (!Array.isArray(models)) return [...issues, 'models: expected array']
  for (let i = 0; i < results.length; i++) issues.push(...validateResultDoc(results[i]))
  for (let i = 0; i < hardware.length; i++) issues.push(...validateHardwareEntry(hardware[i]))
  for (let i = 0; i < runtimes.length; i++) issues.push(...validateRuntimeEntry(runtimes[i]))
  for (let i = 0; i < models.length; i++) issues.push(...validateModelEntry(models[i]))
  if (d.leaderboard !== undefined) issues.push(...validateLeaderboardViews(d.leaderboard))
  if (d.trends !== undefined) issues.push(...validateTrends(d.trends))
  return issues
}

/**
 * Validate and, on contract violations, throw a descriptive error so the UI
 * shows its error state instead of rendering undefined fields.
 */
export function assertDataset(d: unknown): asserts d is Dataset {
  const issues = validateDataset(d)
  if (issues.length === 0) return
  const shown = issues.slice(0, 5).join('; ')
  const more = issues.length > 5 ? ` (+${issues.length - 5} more)` : ''
  throw new Error(`Dataset failed runtime contract validation: ${shown}${more}`)
}