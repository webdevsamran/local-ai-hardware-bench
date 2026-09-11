// Prerender every route to static HTML, then emit sitemap.xml, robots.txt
// and the GitHub Pages 404 fallback.
//
// Why this exists: the dashboard is a client-rendered SPA served from GitHub
// Pages. Before this, every page shared one URL and one <title>, so no page
// could rank for its own subject. This writes a real HTML file per route,
// with that route's content and metadata already in it.
//
// Run after `vite build` (see package.json). Reads the built client output in
// dist/ and the SSR bundle in dist-ssr/.

import { readFileSync, writeFileSync, mkdirSync, existsSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
const WEB = resolve(HERE, '..')
const DIST = join(WEB, 'dist')
const SSR = join(WEB, 'dist-ssr', 'entry-server.js')
const DATA = join(WEB, 'public', 'data')

const BASE = process.env.VITE_BASE_PATH || '/'

function loadDataset() {
  const names = [
    'index',
    'results',
    'hardware',
    'runtimes',
    'models',
    'leaderboard',
    'trends',
    'constants',
    'comparability',
    'pareto',
    'recommend',
    'privacy',
    'cliff',
    'kvcache',
  ]
  // Kept in step with the browser's list in src/lib/data.ts. A file missing
  // here does not crash the prerender -- seedDataset bypasses the runtime
  // validator -- it silently renders the page's empty state into the static
  // HTML, which is worse: the deployed page then ships wrong content.
  const dataset = {}
  for (const name of names) {
    dataset[name] = JSON.parse(
      readFileSync(join(DATA, `${name}.json`), 'utf-8'),
    )
  }
  return dataset
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

/** Absolute URL for a route, honouring the deploy sub-path. */
function urlFor(siteUrl, path) {
  return path === '/' ? siteUrl : `${siteUrl}${path}`
}

/**
 * Structured data so search engines can read the dataset as a dataset.
 * Only the home page carries it; repeating it on every route adds noise.
 */
function datasetJsonLd(siteUrl) {
  return {
    '@context': 'https://schema.org',
    '@type': 'Dataset',
    name: 'AIHWBench local AI hardware benchmark results',
    description:
      'Reproducible benchmarks of local AI inference runtimes across CPUs, GPUs and NPUs, with full environment metadata and an explicit comparison-safety classification for every pair of results.',
    url: siteUrl,
    license: 'https://www.apache.org/licenses/LICENSE-2.0',
    isAccessibleForFree: true,
    creator: {
      '@type': 'Organization',
      name: 'AIHWBench',
      url: 'https://github.com/webdevsamran/local-ai-hardware-bench',
    },
    variableMeasured: [
      'generation tokens per second',
      'time to first token',
      'prompt tokens per second',
      'peak VRAM',
      'average power draw',
      'performance per watt',
    ],
    distribution: [
      {
        '@type': 'DataDownload',
        encodingFormat: 'application/json',
        contentUrl: `${siteUrl}/data/results.json`,
      },
    ],
    measurementTechnique:
      'Local inference benchmarking with fixed prompt, seed, temperature, context length, warm-up and iteration policy; environment recorded per run.',
    keywords: [
      'local LLM benchmark',
      'GPU inference performance',
      'tokens per second',
      'on-device AI',
      'NPU benchmark',
      'performance per watt',
    ],
  }
}

/** Whether a concrete path was generated from a route pattern. */
function pathMatchesPattern(actual, pattern) {
  if (pattern === '*') return false
  const a = actual.split('/').filter(Boolean)
  const b = pattern.split('/').filter(Boolean)
  if (a.length !== b.length) return false
  return b.every((segment, i) => segment.startsWith(':') || segment === a[i])
}

/**
 * `<link rel="modulepreload">` for the chunk this route needs to hydrate.
 *
 * Route components are code-split, so without this the browser discovers the
 * route chunk only after the entry script has parsed and React.lazy asks for
 * it — a request it could have started at the same time as the entry. One
 * preload per page, not all of them: preloading thirty chunks would undo the
 * splitting.
 *
 * Returns nothing when the manifest has no entry for the module. A preload
 * pointing at a chunk that does not exist is a 404 on every page load, which
 * is worse than the waterfall it was meant to remove.
 */
function preloadForRoute(manifest, base, routePath, routeModules) {
  const moduleName = routeModules.get(routePath)
  if (!moduleName) return ''
  const entry = manifest[moduleName]
  if (!entry || !entry.file) return ''
  const href = `${base.replace(/[/]$/, '')}/${entry.file}`
  return `<link rel="modulepreload" href="${escapeHtml(href)}" />`
}

/**
 * Names the one page whose markup does not describe its own URL.
 *
 * Kept in step with `web/src/main.tsx`, which reads it to decide between
 * hydrating and rendering; `tests/test_frontend_hydration.py` asserts the two
 * spellings still match, because a typo here is silent on every page that is
 * prerendered and wrong on every page that is not.
 */
const FALLBACK_MARKER = 'aihwbench-fallback'

function buildHead(meta, siteUrl, extraJsonLd) {
  const canonical = urlFor(siteUrl, meta.path)
  const tags = [
    `<title>${escapeHtml(meta.title)}</title>`,
    `<meta name="description" content="${escapeHtml(meta.description)}" />`,
    `<link rel="canonical" href="${escapeHtml(canonical)}" />`,
    `<meta property="og:type" content="website" />`,
    `<meta property="og:site_name" content="AIHWBench" />`,
    `<meta property="og:title" content="${escapeHtml(meta.title)}" />`,
    `<meta property="og:description" content="${escapeHtml(meta.description)}" />`,
    `<meta property="og:url" content="${escapeHtml(canonical)}" />`,
    `<meta name="twitter:card" content="summary_large_image" />`,
    `<meta name="twitter:title" content="${escapeHtml(meta.title)}" />`,
    `<meta name="twitter:description" content="${escapeHtml(meta.description)}" />`,
  ]
  if (meta.noindex) {
    tags.push(`<meta name="robots" content="noindex, follow" />`)
  }
  if (extraJsonLd) {
    tags.push(
      `<script type="application/ld+json">${JSON.stringify(extraJsonLd)}</script>`,
    )
  }
  return tags.join('\n    ')
}

/** Replace the template's placeholder head and inject the rendered body. */
function composePage(template, headHtml, bodyHtml) {
  let out = template

  // Drop the template's own title/description; the per-route ones replace them.
  out = out.replace(/<title>[\s\S]*?<\/title>\s*/i, '')
  out = out.replace(/<meta\s+name="description"[\s\S]*?\/>\s*/i, '')

  out = out.replace('</head>', `  ${headHtml}\n  </head>`)
  out = out.replace(
    '<div id="root"></div>',
    `<div id="root">${bodyHtml}</div>`,
  )
  return out
}

function writePage(routePath, html) {
  const rel = routePath === '/' ? 'index.html' : `${routePath.slice(1)}/index.html`
  const target = join(DIST, rel)
  mkdirSync(dirname(target), { recursive: true })
  writeFileSync(target, html, 'utf-8')
  return rel
}

function buildSitemap(siteUrl, routes) {
  const urls = routes
    .map((path) => {
      // Landing pages people search for outrank deep result permalinks.
      const priority =
        path === '/'
          ? '1.0'
          : path.split('/').filter(Boolean).length === 1
            ? '0.8'
            : '0.6'
      return [
        '  <url>',
        `    <loc>${escapeHtml(urlFor(siteUrl, path))}</loc>`,
        `    <changefreq>weekly</changefreq>`,
        `    <priority>${priority}</priority>`,
        '  </url>',
      ].join('\n')
    })
    .join('\n')
  return `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls}\n</urlset>\n`
}

async function main() {
  if (!existsSync(SSR)) {
    console.error(
      `prerender: SSR bundle missing at ${SSR}.\n` +
        'Run: vite build --ssr src/entry-server.tsx --outDir dist-ssr',
    )
    process.exit(1)
  }

  const { prepare, render, allRoutes, indexableRoutes, metaForPath, SITE_URL, ROUTES } =
    await import(pathToFileURL(SSR).href)

  // Route components are code-split for the browser. `renderToString` cannot
  // suspend, so they are all loaded before anything is rendered -- otherwise a
  // route still in flight writes its loading fallback into the static HTML,
  // which is the copy a crawler indexes.
  await prepare()

  const dataset = loadDataset()
  const template = readFileSync(join(DIST, 'index.html'), 'utf-8')
  const routes = allRoutes(dataset)

  // SITE_URL already includes the repository sub-path for GitHub Pages.
  const siteUrl = SITE_URL.replace(/\/$/, '')

  // Vite writes this only when `build.manifest` is on; a build without it
  // still prerenders, just without the preload hint.
  const manifestPath = join(DIST, '.vite', 'manifest.json')
  const manifest = existsSync(manifestPath)
    ? JSON.parse(readFileSync(manifestPath, 'utf-8'))
    : {}

  // Concrete route paths are generated from patterns like '/models/:slug', so
  // the pattern's module is found by matching the generated path back to it.
  const routeModules = new Map()
  for (const routePath of routes) {
    const match = ROUTES.find((def) => pathMatchesPattern(routePath, def.path))
    if (match) routeModules.set(routePath, match.module)
  }

  let written = 0
  for (const routePath of routes) {
    const meta = metaForPath(routePath, dataset)
    const body = render(routePath, dataset)
    const head =
      buildHead(meta, siteUrl, routePath === '/' ? datasetJsonLd(siteUrl) : null) +
      preloadForRoute(manifest, BASE, routePath, routeModules)
    writePage(routePath, composePage(template, head, body))
    written += 1
  }

  // GitHub Pages has no server-side rewrite: a deep link that was not
  // prerendered would 404. Serving the home shell from 404.html lets the
  // client router recover the route.
  //
  // The marker matters now that the client hydrates. This one file is served
  // at URLs it does not describe -- its body is the home page, the address bar
  // says /results/whatever -- so it is the one prerendered document the client
  // must NOT adopt. Without the marker every deep link to an unpublished route
  // would hydrate home's markup against a different route's render, mismatch,
  // and recover by doing what the marker asks for directly, with a console
  // error on the way.
  const notFoundMeta = metaForPath('/', dataset)
  writeFileSync(
    join(DIST, '404.html'),
    composePage(
      template,
      buildHead(notFoundMeta, siteUrl, null) +
        `\n  <meta name="${FALLBACK_MARKER}" content="1" />`,
      render('/', dataset),
    ),
    'utf-8',
  )

  // Not `routes`: embed cards are prerendered but must not be indexed, and
  // listing a noindex page in the sitemap asks a crawler to do two
  // contradictory things.
  writeFileSync(
    join(DIST, 'sitemap.xml'),
    buildSitemap(siteUrl, indexableRoutes(dataset)),
    'utf-8',
  )
  writeFileSync(
    join(DIST, 'robots.txt'),
    `User-agent: *\nAllow: /\n\nSitemap: ${siteUrl}/sitemap.xml\n`,
    'utf-8',
  )
  // GitHub Pages otherwise runs the output through Jekyll, which drops
  // files and directories beginning with an underscore.
  writeFileSync(join(DIST, '.nojekyll'), '', 'utf-8')

  console.log(
    `prerender: ${written} route(s) -> dist/, plus sitemap.xml, robots.txt, 404.html (base ${BASE})`,
  )
}

main().catch((error) => {
  console.error('prerender failed:', error)
  process.exit(1)
})
