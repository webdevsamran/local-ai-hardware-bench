// Browser-side comparison-safety classifier.
//
// `aihwbench/comparability.py` stays canonical. The dashboard needs the same
// verdict for any pair a reader selects, and the pair is chosen at runtime, so
// it cannot be precomputed — the logic has to exist here too.
//
// The rule tables are not duplicated: they are generated into
// `data/comparability.json` from the Python module, which also carries
// reference verdicts that the tests replay through this implementation. A
// change to either side that alters a verdict fails the build.
//
// The classifier never picks a winner. It decides only whether a comparison
// may honestly be made.

import type { BenchmarkResultDoc, ComparabilityRules } from './types'

export const STRICTLY_COMPARABLE = 'STRICTLY_COMPARABLE'
export const CONDITIONALLY_COMPARABLE = 'CONDITIONALLY_COMPARABLE'
export const NOT_COMPARABLE = 'NOT_COMPARABLE'

export type Verdict =
  | typeof STRICTLY_COMPARABLE
  | typeof CONDITIONALLY_COMPARABLE
  | typeof NOT_COMPARABLE

export interface Classification {
  classification: Verdict
  reasons: string[]
  machine_reasons: string[]
}

/** Read a dotted path, returning undefined rather than throwing. */
function get(doc: unknown, path: string): unknown {
  let value: unknown = doc
  for (const part of path.split('.')) {
    if (value === null || typeof value !== 'object') return undefined
    value = (value as Record<string, unknown>)[part]
  }
  return value ?? undefined
}

function isMissing(value: unknown): boolean {
  return value === undefined || value === null
}

/**
 * Two absent values agree; one absent and one present do not.
 *
 * Mirrors `_same` in the Python module, including the deliberate asymmetry:
 * a field neither result recorded is genuine agreement about an optional
 * field, but a field only one recorded is a difference.
 */
function same(a: unknown, b: unknown): boolean {
  if (isMissing(a) && isMissing(b)) return true
  if (isMissing(a) || isMissing(b)) return false
  return a === b
}

export function classify(
  rules: ComparabilityRules,
  a: BenchmarkResultDoc | undefined,
  b: BenchmarkResultDoc | undefined,
): Classification {
  const reasons: string[] = []
  const machine: string[] = []

  if (!a || !b) {
    return {
      classification: NOT_COMPARABLE,
      reasons: ['two results are required for a comparison'],
      machine_reasons: [rules.insufficient_metadata_reason],
    }
  }

  // Rule 1: required provenance must be present on both sides. Absence of
  // evidence is not evidence of sameness.
  const missing = rules.required_present.filter(
    (path) => isMissing(get(a, path)) || isMissing(get(b, path)),
  )

  const strictDiffs = rules.strict.filter((path) => !same(get(a, path), get(b, path)))
  const conditionalDiffs = rules.conditional.filter(
    (path) => !same(get(a, path), get(b, path)),
  )

  for (const path of strictDiffs) {
    if (isMissing(get(a, path)) && isMissing(get(b, path))) continue
    const va = get(a, path)
    const vb = get(b, path)
    reasons.push(
      path === 'model.name'
        ? `models differ: ${String(va)} vs ${String(vb)}`
        : `${path}: ${String(va)} vs ${String(vb)}`,
    )
    machine.push(path)
  }

  for (const path of conditionalDiffs) {
    if (isMissing(get(a, path)) && isMissing(get(b, path))) continue
    reasons.push(
      `${path} differs (${String(get(a, path))} vs ${String(get(b, path))}) - interpret as conditional`,
    )
    machine.push(path)
  }

  if (get(a, 'system.cpu') !== get(b, 'system.cpu') || get(a, 'system.gpu') !== get(b, 'system.gpu')) {
    reasons.push('hardware differs between results - treat as cross-platform reference only')
    machine.push('system.hardware')
  }

  if (missing.length > 0) {
    reasons.push(
      `required provenance is missing, so these results cannot be compared: ${missing.join(', ')}`,
    )
    machine.push(rules.insufficient_metadata_reason)
  }

  let classification: Verdict
  if (missing.length > 0 || strictDiffs.length > 0) {
    classification = NOT_COMPARABLE
  } else if (machine.length > 0) {
    classification = CONDITIONALLY_COMPARABLE
  } else {
    classification = STRICTLY_COMPARABLE
  }

  return {
    classification,
    reasons,
    machine_reasons: Array.from(new Set(machine)).sort(),
  }
}

/** Human-readable one-liner for a verdict badge. */
export function verdictSummary(verdict: Verdict): string {
  switch (verdict) {
    case STRICTLY_COMPARABLE:
      return 'Every materially relevant dimension matches. These numbers may be compared directly.'
    case CONDITIONALLY_COMPARABLE:
      return 'The experiment matches, but something worth stating differs. Read the deltas with the caveats below.'
    default:
      return 'These runs measured different things, or did not record enough to tell. A direct comparison would mislead.'
  }
}
