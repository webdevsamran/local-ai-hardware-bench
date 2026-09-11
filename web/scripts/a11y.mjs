// Runs axe-core over every prerendered page and fails the build on a violation.
//
// It reads `dist/`, not a mocked component render, because the prerendered
// HTML is the artifact: it is what a crawler indexes, what a screen reader
// receives before hydration, and what someone on a slow connection sees for
// the first second. A component that behaves in a unit test and ships a broken
// landmark structure is a passing test and a broken page.
//
// **What this cannot check.** jsdom has no layout engine, so `color-contrast`
// -- the rule people most expect from an accessibility run -- errors out and
// is reported as *unevaluated* rather than folded into the pass count, because
// "we did not look" and "we looked and it was fine" are different claims and
// only one of them is true here. Contrast is checked instead by
// `tests/test_heatmap_contrast.py`, which recomputes the ratio from the CSS
// tokens, and by the browser measurement in docs/research/.
//
// Two more rules error under jsdom -- `landmark-one-main` and
// `page-has-heading-one`. Neither actually needs layout, and both are cheap to
// decide directly, so they are checked here as STRUCTURAL_CHECKS instead of
// being written off as unevaluated. A rule that can be covered should be
// covered; the unevaluated list is for what genuinely cannot be.
//
// One jsdom realm is reused for every page, and each page is written into it
// with document.write. A fresh JSDOM per page looks cleaner and does not work:
// axe tests its context with `instanceof window.Node` against the window it
// bound at import, so every page after the first throws "arguments are
// invalid" -- which reads like a bad call site rather than a realm mismatch.
//
// Usage:
//   node scripts/a11y.mjs              # gate: exits 1 on any violation
//   node scripts/a11y.mjs --json out   # also write the full report

import { mkdirSync, readdirSync, readFileSync, statSync, writeFileSync } from 'node:fs'
import { dirname, join, relative, resolve } from 'node:path'
import { JSDOM, VirtualConsole } from 'jsdom'

const argv = process.argv.slice(2)
const DIST = resolve(argv.find((a) => a.startsWith('--dist='))?.slice(7) ?? 'dist')
const JSON_OUT = argv.includes('--json') ? argv[argv.indexOf('--json') + 1] : null

const TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa', 'best-practice']

/** Globals axe reads off the global object rather than off the context it is handed. */
const GLOBALS = [
  'window',
  'document',
  'Node',
  'Element',
  'HTMLElement',
  'NodeList',
  'getComputedStyle',
  'SVGElement',
  'Document',
  'DocumentFragment',
  'ShadowRoot',
  'Text',
  'Comment',
  'Range',
  'MutationObserver',
  'Event',
  'CustomEvent',
  'XMLHttpRequest',
]

/**
 * Rules axe cannot decide under jsdom that do not actually need a layout
 * engine. Checked directly rather than listed as unevaluated.
 */
const STRUCTURAL_CHECKS = [
  {
    id: 'landmark-one-main',
    help: 'The page must have exactly one main landmark',
    impact: 'moderate',
    helpUrl: 'https://dequeuniversity.com/rules/axe/4.13/landmark-one-main',
    check(doc) {
      const mains = doc.querySelectorAll('main, [role="main"]')
      if (mains.length === 1) return null
      return mains.length === 0
        ? 'no <main> landmark, so "skip to content" has nowhere to land'
        : `${mains.length} main landmarks; a screen reader cannot tell which is the content`
    },
  },
  {
    id: 'page-has-heading-one',
    help: 'The page must contain a level-one heading',
    impact: 'moderate',
    helpUrl: 'https://dequeuniversity.com/rules/axe/4.13/page-has-heading-one',
    check(doc) {
      const h1s = doc.querySelectorAll('h1, [role="heading"][aria-level="1"]')
      return h1s.length >= 1 ? null : 'no <h1>, so the page has no name in a heading outline'
    },
  },
]

function htmlFiles(dir) {
  const found = []
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry)
    if (statSync(full).isDirectory()) found.push(...htmlFiles(full))
    else if (entry.endsWith('.html')) found.push(full)
  }
  return found.sort()
}

/** `dist/models/foo/index.html` -> `/models/foo`, which is how a reader names it. */
function routeOf(file) {
  const rel = relative(DIST, file).replaceAll('\\', '/')
  if (rel === 'index.html') return '/'
  if (rel === '404.html') return '/404.html'
  return '/' + rel.replace(/\/index\.html$/, '').replace(/\.html$/, '')
}

const files = htmlFiles(DIST)
if (files.length === 0) {
  console.error(`No HTML under ${DIST}. Run \`npm run build\` first.`)
  process.exit(2)
}

// Silence jsdom's "not implemented" noise (canvas, navigation) without hiding
// a genuine parse failure.
const virtualConsole = new VirtualConsole()
virtualConsole.on('jsdomError', (error) => {
  if (!/Not implemented/.test(error.message)) console.error(error.message)
})

const dom = new JSDOM('<!doctype html><html><head></head><body></body></html>', {
  pretendToBeVisual: true,
  virtualConsole,
})
for (const key of GLOBALS) {
  if (dom.window[key] === undefined) continue
  // Plain assignment fails for getter-only globals, so define.
  Object.defineProperty(globalThis, key, {
    value: dom.window[key],
    configurable: true,
    writable: true,
  })
}
const axe = (await import('axe-core')).default

const pages = []
const byRule = new Map()
const unevaluated = new Set()

for (const file of files) {
  const route = routeOf(file)
  const doc = dom.window.document
  doc.open()
  doc.write(readFileSync(file, 'utf8'))
  doc.close()

  const result = await axe.run(doc, { runOnly: { type: 'tag', values: TAGS } })

  const violations = result.violations.map((v) => ({
    id: v.id,
    impact: v.impact,
    help: v.help,
    helpUrl: v.helpUrl,
    nodes: v.nodes.map((n) => ({ target: n.target, html: n.html.slice(0, 200) })),
  }))

  for (const structural of STRUCTURAL_CHECKS) {
    const failure = structural.check(doc)
    if (failure === null) continue
    violations.push({
      id: structural.id,
      impact: structural.impact,
      help: structural.help,
      helpUrl: structural.helpUrl,
      nodes: [{ target: ['html'], html: failure }],
    })
  }

  const structuralIds = new Set(STRUCTURAL_CHECKS.map((s) => s.id))
  for (const i of result.incomplete) {
    if (!structuralIds.has(i.id)) unevaluated.add(i.id)
  }

  for (const v of violations) {
    const seen = byRule.get(v.id) ?? { rule: v, routes: [] }
    seen.routes.push(route)
    byRule.set(v.id, seen)
  }

  pages.push({
    route,
    file: relative(DIST, file).replaceAll('\\', '/'),
    violations,
    unevaluated: result.incomplete.map((i) => i.id).filter((id) => !structuralIds.has(id)),
    axe_rules_passed: result.passes?.length ?? null,
  })
}

const total = pages.reduce((n, p) => n + p.violations.length, 0)

console.log(`axe-core ${axe.version} over ${pages.length} prerendered pages under ${DIST}\n`)

if (total === 0) {
  // The per-page count varies with what each page contains -- a page with no
  // table cannot pass the table rules -- so report the range rather than one
  // page's number as though it were everyone's.
  const passed = pages.map((p) => p.axe_rules_passed ?? 0)
  const low = Math.min(...passed)
  const high = Math.max(...passed)
  const rules = low === high ? `${low}` : `${low}-${high}`
  console.log(
    `No violations. ${rules} axe rules passed per page, plus ${STRUCTURAL_CHECKS.length} structural checks on each.`,
  )
} else {
  for (const [id, { rule, routes }] of [...byRule.entries()].sort()) {
    console.log(`${(rule.impact ?? 'unknown').toUpperCase()}  ${id} — ${rule.help}`)
    const shown = routes.slice(0, 6).join(', ')
    console.log(`  ${routes.length} page(s): ${shown}${routes.length > 6 ? ` … +${routes.length - 6}` : ''}`)
    for (const node of rule.nodes.slice(0, 2)) {
      console.log(`  ${node.target.join(' ')}`)
      console.log(`    ${node.html.slice(0, 160).replace(/\s+/g, ' ')}`)
    }
    console.log(`  ${rule.helpUrl}\n`)
  }
}

// Not a footnote. A rule that could not be decided is unchecked, and saying so
// is the difference between this report and a false all-clear.
if (unevaluated.size > 0) {
  console.log(
    `\nNot evaluated (${unevaluated.size}): ${[...unevaluated].sort().join(', ')}\n` +
      '  jsdom has no layout engine, so these cannot return a verdict here.\n' +
      '  They are unchecked by this run, not passing. Contrast is covered by\n' +
      '  tests/test_heatmap_contrast.py and by the browser measurement in\n' +
      '  docs/research/dashboard-performance.md.',
  )
}

if (JSON_OUT) {
  mkdirSync(dirname(resolve(JSON_OUT)), { recursive: true })
  writeFileSync(
    resolve(JSON_OUT),
    JSON.stringify(
      {
        tool: 'axe-core',
        version: axe.version,
        tags: TAGS,
        pages_checked: pages.length,
        violations_total: total,
        structural_checks: STRUCTURAL_CHECKS.map((s) => s.id),
        rules_not_evaluated: [...unevaluated].sort(),
        not_evaluated_note:
          'jsdom has no layout engine; these rules errored and are unchecked, not passing.',
        pages,
      },
      null,
      2,
    ) + '\n',
  )
  console.log(`\nReport written to ${JSON_OUT}`)
}

process.exit(total === 0 ? 0 : 1)
