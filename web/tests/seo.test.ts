import { describe, it, expect } from 'vitest'
import { allRoutes, metaForPath } from '../src/lib/seo'
import type { Dataset } from '../src/lib/types'

// A page that shares another page's title and description cannot rank for its
// own subject, and the site previously served one title for every route.
// These tests keep each route's identity distinct.

const dataset = {
  index: {
    schema_version: '1.0',
    results_count: 1,
    hardware_count: 1,
    runtime_count: 1,
    model_count: 1,
    source_dir: 'results/published',
    note: '',
  },
  results: [
    {
      run_id: 'ollama-123',
      model: { name: 'qwen2.5:0.5b-instruct-q4_K_M' },
      system: { gpu: 'NVIDIA RTX 3080 Ti Laptop' },
    },
  ],
  hardware: [
    {
      fingerprint: 'hwfp-v2-abc',
      cpu: 'Intel i9-12900H',
      gpu: 'NVIDIA RTX 3080 Ti Laptop',
      npu: null,
      os: 'Windows 11',
      ram_gb: 32,
      result_ids: ['ollama-123'],
    },
  ],
  runtimes: [
    {
      name: 'ollama',
      versions: ['0.32.15'],
      device_options: ['cuda'],
      result_ids: ['ollama-123'],
    },
  ],
  models: [
    {
      name: 'qwen2.5:0.5b-instruct-q4_K_M',
      format: 'gguf',
      quantizations: ['q4_K_M'],
      checksums: [],
      result_ids: ['ollama-123'],
    },
  ],
  leaderboard: {},
  trends: {},
} as unknown as Dataset

describe('metaForPath', () => {
  it('gives every route a distinct title and description', () => {
    const routes = allRoutes(dataset)
    const titles = new Set<string>()
    const descriptions = new Set<string>()
    for (const route of routes) {
      const meta = metaForPath(route, dataset)
      expect(meta.title, `${route} has no title`).toBeTruthy()
      expect(meta.description.length, `${route} description too short`).toBeGreaterThan(50)
      titles.add(meta.title)
      descriptions.add(meta.description)
    }
    expect(titles.size).toBe(routes.length)
    expect(descriptions.size).toBe(routes.length)
  })

  it('describes a model page using the measured model', () => {
    const meta = metaForPath('/models/qwen2-5-0-5b-instruct-q4_k_m', dataset)
    expect(meta.title).toContain('qwen2.5:0.5b-instruct-q4_K_M')
    expect(meta.description).toContain('q4_K_M')
  })

  it('describes a hardware page using the measured machine', () => {
    const meta = metaForPath('/hardware/hwfp-v2-abc', dataset)
    expect(meta.title).toContain('RTX 3080 Ti')
    expect(meta.description).toContain('i9-12900H')
  })

  it('still yields a route-specific title without the dataset', () => {
    // The prerenderer always has the dataset, but client navigation can run
    // before it loads. Falling back to the home page's title would duplicate
    // it across every URL.
    const meta = metaForPath('/models/some-model')
    expect(meta.title).toContain('some-model')
    expect(meta.title).not.toBe(metaForPath('/').title)
  })

  it('treats a trailing slash as the same route', () => {
    expect(metaForPath('/leaderboard/').title).toBe(metaForPath('/leaderboard').title)
  })

  it('includes every dataset entity in the route list', () => {
    const routes = allRoutes(dataset)
    expect(routes).toContain('/models/qwen2-5-0-5b-instruct-q4_k_m')
    expect(routes).toContain('/hardware/hwfp-v2-abc')
    expect(routes).toContain('/runtimes/ollama')
    expect(routes).toContain('/results/ollama-123')
  })

  it('gives every measured model-on-GPU pair its own route', () => {
    // "How fast is X on a Y" is the query people type, and it is a different
    // question from either half. It needs its own indexable URL.
    const routes = allRoutes(dataset)
    expect(routes).toContain(
      '/models/qwen2-5-0-5b-instruct-q4_k_m/on/nvidia-rtx-3080-ti-laptop',
    )
  })

  it('does not invent a page for an unmeasured pair', () => {
    // A page promising a number it does not have is worse than no page.
    const routes = allRoutes(dataset)
    expect(routes).not.toContain('/models/qwen2-5-0-5b-instruct-q4_k_m/on/rtx-4090')
  })

  it('describes a combination page with both halves', () => {
    const meta = metaForPath(
      '/models/qwen2-5-0-5b-instruct-q4_k_m/on/nvidia-rtx-3080-ti-laptop',
      dataset,
    )
    expect(meta.title).toContain('qwen2.5:0.5b-instruct-q4_K_M')
    expect(meta.title).toContain('RTX 3080 Ti')
    expect(meta.description).toContain('peak VRAM')
  })

  it('never emits a duplicate route', () => {
    const routes = allRoutes(dataset)
    expect(new Set(routes).size).toBe(routes.length)
  })
})
