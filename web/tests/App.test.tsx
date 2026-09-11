import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { AppRoutes, AppShell } from '../src/App'
import Layout from '../src/components/Layout'

import { dataset, indexDoc } from './fixtures/dataset'


beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) => {
      const map: Record<string, unknown> = {
        'data/index.json': indexDoc,
        'data/results.json': dataset.results,
        'data/hardware.json': dataset.hardware,
        'data/runtimes.json': dataset.runtimes,
        'data/models.json': dataset.models,
        'data/leaderboard.json': dataset.leaderboard,
        'data/trends.json': dataset.trends,
        'data/constants.json': dataset.constants,
        'data/comparability.json': dataset.comparability,
        'data/pareto.json': dataset.pareto,
        'data/recommend.json': dataset.recommend,
        'data/privacy.json': dataset.privacy,
        'data/cliff.json': dataset.cliff,
        'data/kvcache.json': dataset.kvcache,
      }
      // The app requests base-anchored URLs (`/data/x.json`, or
      // `/local-ai-hardware-bench/data/x.json` in production) because a
      // relative path would 404 on deep routes under BrowserRouter. Match on
      // the tail so the mock does not depend on the deploy base.
      const key = Object.keys(map).find((k) => url.endsWith(k))
      const body = key === undefined ? undefined : map[key]
      return Promise.resolve({
        ok: body !== undefined,
        status: body !== undefined ? 200 : 404,
        json: () => Promise.resolve(body),
      })
    }),
  )
})

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Layout>
        <AppRoutes />
      </Layout>
    </MemoryRouter>,
  )
}

/**
 * Render through `AppShell` rather than `AppRoutes`.
 *
 * `AppShell` is where the decision to drop the site chrome for `/embed/`
 * lives, so an embed route rendered through `AppRoutes` alone falls through to
 * NotFound. The browser and the prerenderer both go through `AppShell`; the
 * test has to as well, or it is exercising a path nothing uses.
 */
function renderShellAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AppShell />
    </MemoryRouter>,
  )
}

describe('App routes (smoke)', () => {
  it('renders home with dataset stats', async () => {
    renderAt('/')
    const ones = await screen.findAllByText('1')
    expect(ones.length).toBeGreaterThanOrEqual(4)
    expect(screen.getByText('Published results')).toBeTruthy()
  })

  it('renders leaderboard rows from real data', async () => {
    renderAt('/leaderboard')
    expect(await screen.findByText('test-run-1')).toBeTruthy()
  })

  it('renders hardware explorer', async () => {
    renderAt('/hardware')
    expect(await screen.findByText('Test CPU')).toBeTruthy()
  })

  it('answers the will-it-run wizard from the generated constants', async () => {
    renderAt('/will-it-run')
    // 7B at q4_k_m is ~4.9 GB with overhead, which fits the 8 GB default.
    expect(await screen.findByText(/Fits entirely in VRAM/)).toBeTruthy()
  })

  it('filters the leaderboard from the URL query string', async () => {
    // Filters live in the URL so a filtered view is shareable and survives a
    // reload. The fixture's single result is on ollama, so filtering to a
    // different runtime must empty the table rather than ignore the filter.
    renderAt('/leaderboard?runtime=llama.cpp')
    expect(await screen.findByText(/No result matches these filters/)).toBeTruthy()
  })

  it('shows the leaderboard when a filter matches', async () => {
    renderAt('/leaderboard?runtime=ollama')
    expect(await screen.findByText('test-run-1')).toBeTruthy()
  })

  it('draws the VRAM cliff on the wizard', async () => {
    renderAt('/will-it-run')
    // The chart is labelled with the size at which the model becomes fully
    // resident, so a screen reader gets the number and not just "chart".
    expect(
      await screen.findByLabelText(/Share of the model running outside VRAM/),
    ).toBeTruthy()
  })

  it('tells the local-vs-cloud page it has no power data to work from', async () => {
    // The fixture result has no average_power_watts, so the local running
    // cost is not computable. The page must say so rather than quietly
    // assuming a power figure.
    renderAt('/local-vs-cloud')
    expect(
      await screen.findByText(/No published result measured both power draw/),
    ).toBeTruthy()
  })

  it('renders result detail for a known run', async () => {
    renderAt('/results/test-run-1')
    expect(await screen.findByText('Reproducibility')).toBeTruthy()
  })

  it('renders not-found page for unknown routes', async () => {
    renderAt('/nope/nope')
    expect(await screen.findByText(/404/)).toBeTruthy()
  })
})
// --- Pages added after the initial route set --------------------------------
//
// Each of these can render an empty state that looks like a working page, so
// the assertions check for content the page can only produce from data — the
// failure being guarded against is a route that silently renders nothing.

describe('later routes (smoke)', () => {
  it('renders the matchmaker with a verdict', async () => {
    renderAt('/matchmaker')
    expect(await screen.findByText(/Which model should I run/)).toBeTruthy()
    // The thresholds it applied must be visible, since they are judgements
    // rather than measurements.
    expect(await screen.findByText(/Why these thresholds/)).toBeTruthy()
  })

  it('renders the submission page and promises no upload', async () => {
    renderAt('/submit')
    expect(await screen.findByText(/Submit a result/)).toBeTruthy()
    expect(await screen.findByText(/Nothing is uploaded/)).toBeTruthy()
  })

  it('tells the offload-cliff page when no sweep has been published', async () => {
    // The fixture carries no curves, so the page must say so rather than
    // rendering an empty chart that reads as "no cliff".
    renderAt('/offload-cliff')
    expect(await screen.findByText(/No offload sweep has been published/)).toBeTruthy()
  })

  it('warns about a configuration that costs more memory than it saves', async () => {
    // The measured inversion: a smaller cache that used *more* device memory.
    // It is the one row a reader must not skim past, so the page states it in
    // prose rather than relying on a shaded table row that colour-blind or
    // greyscale readers would not see.
    renderAt('/kv-cache')
    expect(await screen.findByText(/836 MiB more/)).toBeTruthy()
  })

  it('names the best measured configuration rather than leaving it to be inferred', async () => {
    renderAt('/kv-cache')
    expect(await screen.findByText(/71.9% less cache/)).toBeTruthy()
  })

  it('marks a throughput difference inside the noise floor as indistinguishable', async () => {
    // -6.3% is inside the measured run-to-run noise floor. Rendering it as a
    // plain number would invite tuning against the machine.
    renderAt('/kv-cache')
    expect(await screen.findByText(/-6.3% ≈/)).toBeTruthy()
  })

  it('renders an embed card for a known run', async () => {
    renderShellAt('/embed/result/test-run-1')
    // The caveat is the reason the card can be embedded at all.
    expect(await screen.findByText(/Comparable only with results/)).toBeTruthy()
  })

  it('says so when an embed names a run that does not exist', async () => {
    renderShellAt('/embed/result/no-such-run')
    expect(await screen.findByText(/No published result with id/)).toBeTruthy()
  })

  it('renders an embed without the site chrome', async () => {
    // The card sits inside someone else's page, where this site's navigation
    // and footer would be noise wrapped around a small card.
    const { container } = renderShellAt('/embed/result/test-run-1')
    await screen.findByText(/Comparable only with results/)
    expect(container.querySelector('nav')).toBeNull()
    expect(container.querySelector('footer')).toBeNull()
  })

  it('keeps a landmark and a heading after the chrome is dropped', async () => {
    // Dropping the chrome dropped the only structure the document had. An
    // iframe is its own document: a screen reader entering one inherits no
    // landmarks or headings from the host page, so without these the card is
    // an unnavigable block of text. axe found this on all nine prerendered
    // embed pages.
    const { container } = renderShellAt('/embed/result/test-run-1')
    await screen.findByText(/Comparable only with results/)
    expect(container.querySelectorAll('main')).toHaveLength(1)
    const heading = container.querySelector('h1')
    expect(heading?.textContent).toBe('m')
  })
})
