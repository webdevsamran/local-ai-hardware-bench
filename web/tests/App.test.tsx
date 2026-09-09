import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { AppRoutes } from '../src/App'
import Layout from '../src/components/Layout'

// Static dataset fetch mock — mirrors the generated data files.
const indexDoc = {
  schema_version: '1.0',
  results_count: 1,
  hardware_count: 1,
  runtime_count: 1,
  model_count: 1,
  source_dir: 'results/published',
  note: 'test',
}
const resultDoc = {
  schema_version: '1.0',
  run_id: 'test-run-1',
  timestamp: '2026-01-01T00:00:00Z',
  system: { os: 'TestOS', cpu: 'Test CPU', gpu: null },
  runtime: { name: 'ollama', version: '1.0', device: 'cpu' },
  model: { name: 'm', format: 'gguf' },
  metrics: { generation_tokens_per_second: 10.0, ttft_ms: 100.0 },
}
const dataset = {
  index: indexDoc,
  results: [resultDoc],
  hardware: [
    {
      fingerprint: 'fp1',
      cpu: 'Test CPU',
      gpu: null,
      npu: null,
      os: 'TestOS',
      ram_gb: 16,
      result_ids: ['test-run-1'],
    },
  ],
  runtimes: [
    { name: 'ollama', versions: ['1.0'], device_options: ['cpu'], result_ids: ['test-run-1'] },
  ],
  models: [
    { name: 'm', format: 'gguf', quantizations: [], checksums: [], result_ids: ['test-run-1'] },
  ],
  leaderboard: {
    throughput: [
      {
        rank: 1,
        group: 0,
        group_label: 'm on ollama',
        group_size: 1,
        run_id: 'test-run-1',
        runtime: 'ollama',
        model: 'm',
        cpu: 'Test CPU',
        gpu: null,
        value: 10.0,
      },
    ],
    ttft: [],
    perf_watt: [],
  },
  trends: {},
  constants: {
    bits_per_weight: { q4_k_m: 4.85, fp16: 16.0 },
    overhead_factor: 1.15,
    note: 'test constants',
    reference_cases: [],
  },
}

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

  it('renders result detail for a known run', async () => {
    renderAt('/results/test-run-1')
    expect(await screen.findByText('Reproducibility')).toBeTruthy()
  })

  it('renders not-found page for unknown routes', async () => {
    renderAt('/nope/nope')
    expect(await screen.findByText(/404/)).toBeTruthy()
  })
})