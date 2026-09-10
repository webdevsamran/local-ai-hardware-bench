// Browser-side privacy scan, from the CLI's own pattern registry.
//
// `aihwbench/sanitize.py` stays canonical. Its expressions are generated into
// `data/privacy.json` and compiled here, rather than transcribed by hand: two
// copies of these regexes would eventually disagree about whether a file is
// safe to share, and the dangerous direction of that disagreement is silent.
// Nobody notices a scanner that has quietly stopped catching something until
// the leak is already published.
//
// The generated file also carries reference vectors — probe strings with the
// pattern ids Python matched — and web/tests replays them through this
// implementation. Python's `re` and JavaScript's `RegExp` do agree on this
// subset, but that is a claim worth testing rather than assuming.

export interface PrivacyPattern {
  id: string
  label: string
  pattern: string
  ignore_case: boolean
}

export interface PrivacyRules {
  patterns: PrivacyPattern[]
  reference_cases: { text: string; matches: string[] }[]
  note: string
}

export interface PrivacyFinding {
  /** JSON-style path to the offending value, e.g. `$.system.cpu`. */
  path: string
  /** Which pattern fired. */
  pattern: string
  label: string
  /**
   * A short prefix of the match plus its length — never the whole value.
   * A finding is meant to be shown on screen and pasted into an issue, so
   * echoing the secret in full would leak it a second time.
   */
  preview: string
  matchedLength: number
}

const PREVIEW_CHARS = 4

function compile(pattern: PrivacyPattern): RegExp {
  return new RegExp(pattern.pattern, pattern.ignore_case ? 'gi' : 'g')
}

/** Every pattern id matching anywhere in `text`, in registry order. */
export function scanText(text: string, rules: PrivacyRules): string[] {
  const hits: string[] = []
  for (const pattern of rules.patterns) {
    // A fresh RegExp per call: a `g`-flagged one carries `lastIndex` between
    // uses, so a shared instance would skip matches depending on what was
    // scanned before it. That is a bug that only appears at scale, which is
    // exactly when the scan matters.
    if (compile(pattern).test(text)) hits.push(pattern.id)
  }
  return hits
}

/**
 * Walk a parsed result and report every leak with its structural path.
 *
 * Walking the object rather than scanning its JSON text keeps the path
 * (`$.reproducibility.command`) attached to each finding, which is what makes
 * a finding actionable: "there is a home directory in here somewhere" is not
 * something a contributor can fix.
 */
export function scanObject(value: unknown, rules: PrivacyRules): PrivacyFinding[] {
  const findings: PrivacyFinding[] = []

  function walk(node: unknown, path: string): void {
    if (typeof node === 'string') {
      for (const pattern of rules.patterns) {
        const match = compile(pattern).exec(node)
        if (match) {
          findings.push({
            path,
            pattern: pattern.id,
            label: pattern.label,
            preview: `${match[0].slice(0, PREVIEW_CHARS)}…`,
            matchedLength: match[0].length,
          })
        }
      }
      return
    }
    if (Array.isArray(node)) {
      node.forEach((item, index) => walk(item, `${path}[${index}]`))
      return
    }
    if (node && typeof node === 'object') {
      for (const [key, child] of Object.entries(node)) {
        walk(child, `${path}.${key}`)
      }
      return
    }
    // Numbers, booleans and null cannot carry a leak.
  }

  walk(value, '$')
  return findings
}
