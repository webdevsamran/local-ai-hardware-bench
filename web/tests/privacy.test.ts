import { describe, it, expect } from 'vitest'
import { scanObject, scanText, type PrivacyRules } from '../src/lib/privacy'
import privacyJson from '../public/data/privacy.json'

// The browser scan and the CLI scan must agree about whether a file is safe
// to share. They are two regex engines reading one generated pattern list, and
// the reference vectors below were produced by Python — so a divergence fails
// the build rather than quietly letting a leak through on the web path only.
//
// The dangerous direction is silent: a scanner that has stopped catching
// something looks exactly like a clean file.

const rules = privacyJson as unknown as PrivacyRules

describe('pattern registry', () => {
  it('ships the patterns the CLI uses', () => {
    expect(rules.patterns.length).toBeGreaterThan(0)
    for (const pattern of rules.patterns) {
      expect(pattern.id).toBeTruthy()
      expect(pattern.label).toBeTruthy()
      // Compiling here is the check: an expression Python accepts but
      // JavaScript rejects must fail now, not on a contributor's paste.
      expect(() => new RegExp(pattern.pattern, pattern.ignore_case ? 'gi' : 'g')).not.toThrow()
    }
  })

  it('exercises every pattern in its reference vectors', () => {
    // A pattern with no positive vector is untested, and an untested pattern
    // is one nobody would notice had stopped working.
    const covered = new Set(rules.reference_cases.flatMap((c) => c.matches))
    for (const pattern of rules.patterns) {
      expect(covered, `no reference vector matches ${pattern.id}`).toContain(pattern.id)
    }
  })

  it('includes negative vectors', () => {
    // Positives alone would pass for a pattern matching everything.
    const negatives = rules.reference_cases.filter((c) => c.matches.length === 0)
    expect(negatives.length).toBeGreaterThan(0)
  })
})

describe('agreement with the canonical Python scanner', () => {
  for (const testCase of rules.reference_cases) {
    it(`matches Python on ${JSON.stringify(testCase.text).slice(0, 48)}`, () => {
      expect(scanText(testCase.text, rules).sort()).toEqual([...testCase.matches].sort())
    })
  }
})

describe('scanning a result document', () => {
  it('reports the path of each finding', () => {
    // "There is a home directory somewhere in here" is not something a
    // contributor can act on.
    const findings = scanObject(
      { reproducibility: { command: 'aihwbench --model /home/alice/m.gguf' } },
      rules,
    )
    expect(findings).toHaveLength(1)
    expect(findings[0]!.path).toBe('$.reproducibility.command')
    expect(findings[0]!.pattern).toBe('home_path')
  })

  it('walks into arrays', () => {
    const findings = scanObject({ notes: ['fine', 'ping 192.168.1.44'] }, rules)
    expect(findings.map((f) => f.path)).toEqual(['$.notes[1]'])
  })

  it('never echoes the whole matched value', () => {
    // The finding is shown on screen and pasted into issues. Echoing the
    // secret in order to report it would leak it a second time.
    const secret = 'ghp_' + 'b'.repeat(36)
    const findings = scanObject({ token: secret }, rules)
    expect(findings).toHaveLength(1)
    const rendered = JSON.stringify(findings[0])
    expect(rendered).not.toContain(secret)
    expect(findings[0]!.matchedLength).toBe(secret.length)
  })

  it('finds nothing in an ordinary result', () => {
    const findings = scanObject(
      {
        run_id: 'ollama-1789011548-20e39a8f',
        system: {
          cpu: '12th Gen Intel(R) Core(TM) i9-12900H',
          gpu: 'NVIDIA GeForce RTX 3080 Ti Laptop GPU',
        },
        model: { name: 'qwen2.5:0.5b-instruct-q4_K_M' },
        metrics: { generation_tokens_per_second: 281.65 },
      },
      rules,
    )
    expect(findings).toEqual([])
  })

  it('does not skip matches because of a shared regex lastIndex', () => {
    // A `g`-flagged RegExp reused across calls carries `lastIndex`, so a
    // shared instance silently skips matches depending on what was scanned
    // before it — a bug that only shows up once there is enough data for it
    // to matter, which is exactly when the scan counts.
    const doc = {
      a: 'user@example.com',
      b: 'other@example.com',
      c: 'third@example.com',
    }
    const findings = scanObject(doc, rules)
    expect(findings.map((f) => f.path).sort()).toEqual(['$.a', '$.b', '$.c'])
  })

  it('ignores values that cannot carry a leak', () => {
    expect(scanObject({ n: 42, ok: true, missing: null }, rules)).toEqual([])
  })
})
