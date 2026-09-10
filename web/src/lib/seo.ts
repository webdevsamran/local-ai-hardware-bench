// Page metadata: one source of truth for the prerenderer and the client.
//
// The prerenderer writes these into the static <head> of every route, so a
// crawler sees a distinct title and description without executing JavaScript.
// `useSeo` applies the same values on client-side navigation, so the two can
// never drift.

import type { Dataset } from './types'
import { slugify } from './format'

export const SITE_NAME = 'AIHWBench'
export const SITE_URL = 'https://webdevsamran.github.io/local-ai-hardware-bench'

export interface PageMeta {
  title: string
  description: string
  /** Canonical path, without the deploy base. */
  path: string
}

const BRAND = 'AIHWBench — Local AI Hardware Benchmarks'

/** Titles and descriptions for routes that need no dataset lookup. */
const STATIC_META: Record<string, Omit<PageMeta, 'path'>> = {
  '/': {
    title: BRAND,
    description:
      'Vendor-neutral, reproducible benchmarks of local AI runtimes across CPUs, GPUs and NPUs. Every result publishes its full environment, and the dataset states when two numbers cannot honestly be compared.',
  },
  '/leaderboard': {
    title: 'Leaderboard — AIHWBench',
    description:
      'Local AI inference results grouped by comparison safety. Throughput, time to first token and performance per watt, ranked only within groups that are genuinely comparable.',
  },
  '/will-it-run': {
    title: 'Will this LLM run on my PC? — AIHWBench',
    description:
      'Check whether a local LLM fits your GPU before downloading it. Enter your VRAM, RAM, model size and quantization to see estimated memory use, how much would spill to system RAM, and any measured benchmark results for that configuration.',
  },
  '/local-vs-cloud': {
    title: 'Local LLM hardware vs cloud API cost — AIHWBench',
    description:
      'Work out whether buying a GPU costs less than paying per token, using measured power draw and throughput from published benchmarks. Enter your volume, your cloud price and your electricity rate to see the break-even point in months.',
  },
  '/frontiers': {
    title: 'Efficiency frontiers — speed vs power and VRAM — AIHWBench',
    description:
      'Which local AI configurations are not beaten on both axes at once: throughput against power draw, peak VRAM and time to first token. A card that is slower but far more efficient is still on the frontier, which a single ranked leaderboard cannot show.',
  },
  '/matchmaker': {
    title: 'Which local AI model should I run? — AIHWBench',
    description:
      'Four questions about what you want to do — chat, code completion, long documents or agents — answered from published benchmark measurements. Task requirements become throughput floors and latency ceilings, and the page says whether any measured result actually meets them.',
  },
  '/recommend': {
    title: 'What local LLM should I run on my hardware? — AIHWBench',
    description:
      'Get a model size, runtime, device and context length for your GPU and RAM. The size is estimated from your memory budget; the runtime is anchored on benchmarks people actually measured, and the page states which is which.',
  },
  '/hardware': {
    title: 'Hardware — AIHWBench',
    description:
      'Every CPU, GPU and NPU with published local AI benchmark results, including the full driver and runtime environment for each machine.',
  },
  '/runtimes': {
    title: 'Runtimes — AIHWBench',
    description:
      'Benchmarked local inference runtimes — Ollama, llama.cpp, ONNX Runtime, OpenVINO and more — with the devices and versions each was measured on.',
  },
  '/models': {
    title: 'Models — AIHWBench',
    description:
      'Models benchmarked on local hardware, with quantization, format and checksum recorded for every measured run.',
  },
  '/results': {
    title: 'Results — AIHWBench',
    description:
      'Every published benchmark result, with its complete environment, measurement protocol and trust state.',
  },
  '/compare': {
    title: 'Compare results — AIHWBench',
    description:
      'Compare two local AI benchmark results side by side, with an explicit verdict on whether the comparison is safe to make at all.',
  },
  '/dataset': {
    title: 'Open dataset — AIHWBench',
    description:
      'Browse and download the open AIHWBench dataset: schema-validated local AI benchmark results as JSON, CSV and SQLite.',
  },
  '/methodology': {
    title: 'Methodology — AIHWBench',
    description:
      'How AIHWBench measures: controlled variables, metric definitions, the statistical policy, and an explicit list of what the numbers do not capture.',
  },
  '/compatibility': {
    title: 'Compatibility matrix — AIHWBench',
    description:
      'Which local AI runtimes are genuinely tested on which hardware. Untested combinations are marked as untested rather than assumed to work.',
  },
  '/docs': {
    title: 'Documentation — AIHWBench',
    description:
      'Install AIHWBench, run a benchmark on your own hardware, validate the result and submit it to the public dataset.',
  },
  '/community': {
    title: 'Community — AIHWBench',
    description:
      'Contribute benchmark results, add a runtime backend, or lend hardware to the open local AI benchmarking project.',
  },
  '/hardware-needed': {
    title: 'Hardware needed — AIHWBench',
    description:
      'Hardware the project has no access to and therefore cannot benchmark. Results are never claimed for machines that were not measured.',
  },
  '/planned/enterprise': {
    title: 'Enterprise (planned) — AIHWBench',
    description:
      'Planned enterprise capabilities: CI regression gates, fleet dashboards and procurement reporting. Documented as planned, not shipped.',
  },
  '/planned/certification': {
    title: 'Certification (planned) — AIHWBench',
    description:
      'What a future AIHWBench certification mark would mean, defined openly before anything carries one. Nothing is certified today.',
  },
  '/about': {
    title: 'About — AIHWBench',
    description:
      'Why AIHWBench exists: reproducible local AI benchmarks with published raw data, an open methodology, and an honest model of comparability.',
  },
}

function titleCase(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1)
}

function stripTrailingSlash(path: string): string {
  return path.length > 1 && path.endsWith('/') ? path.slice(0, -1) : path
}

/**
 * Metadata for one path.
 *
 * `dataset` is optional. Without it, detail routes still get a route-specific
 * title rather than inheriting the home page's — a duplicated title across
 * hundreds of URLs is worse for ranking than a generic but distinct one.
 */
export function metaForPath(path: string, dataset?: Dataset | null): PageMeta {
  const clean = stripTrailingSlash(path)
  const stat = STATIC_META[clean]
  if (stat) return { ...stat, path: clean }

  const segments = clean.split('/').filter(Boolean)
  const section = segments[0]
  const key = segments[1] ? decodeURIComponent(segments[1]) : undefined

  // /models/<model>/on/<gpu> -- "how fast is X on a Y", which is a different
  // query from either half and deserves its own indexable page.
  if (section === 'models' && key && segments[2] === 'on' && segments[3]) {
    const gpuSlug = decodeURIComponent(segments[3])
    const model = dataset?.models.find((m) => slugify(m.name) === key)
    const hardware = dataset?.hardware.find((h) => slugify(h.gpu ?? '') === gpuSlug)
    const modelName = model?.name ?? key
    const gpuName = hardware?.gpu ?? gpuSlug
    return {
      path: clean,
      title: `${modelName} on ${gpuName} — benchmark — AIHWBench`,
      description: `Measured local inference performance for ${modelName} running on ${gpuName}: tokens per second, time to first token and peak VRAM, with the full environment of every run recorded.`,
    }
  }

  if (section === 'models' && key) {
    const model = dataset?.models.find((m) => slugify(m.name) === key)
    const name = model?.name ?? key
    const quants = model?.quantizations?.filter(Boolean).join(', ')
    return {
      path: clean,
      title: `${name} — local benchmarks — AIHWBench`,
      description: quants
        ? `Measured local inference performance for ${name} (${quants}): tokens per second, time to first token and performance per watt on real consumer hardware.`
        : `Measured local inference performance for ${name} on real consumer hardware, with the full environment of every run published.`,
    }
  }

  if (section === 'hardware' && key) {
    const hw = dataset?.hardware.find((h) => h.fingerprint === key)
    const label = hw ? (hw.gpu ?? hw.cpu) : key
    return {
      path: clean,
      title: `${label} — local AI benchmarks — AIHWBench`,
      description: hw
        ? `Local AI inference benchmarks measured on ${hw.cpu} with ${hw.gpu ?? 'no discrete GPU'} and ${hw.ram_gb} GB RAM: which models run, and how fast.`
        : 'Local AI inference benchmarks measured on this hardware configuration.',
    }
  }

  if (section === 'runtimes' && key) {
    const rt = dataset?.runtimes.find((r) => r.name === key)
    const devices = rt?.device_options?.filter(Boolean).join(', ')
    return {
      path: clean,
      title: `${titleCase(key)} — runtime benchmarks — AIHWBench`,
      description: devices
        ? `Measured performance of the ${key} local inference runtime on ${devices}, with versions and full environment recorded for every run.`
        : `Measured performance of the ${key} local inference runtime on real hardware.`,
    }
  }

  if (section === 'results' && key) {
    return {
      path: clean,
      title: `Result ${key} — AIHWBench`,
      description: `Benchmark result ${key}: measured metrics, complete hardware and runtime environment, measurement protocol and trust state.`,
    }
  }

  return {
    path: clean,
    title: 'Not found — AIHWBench',
    description: 'This page does not exist in the AIHWBench dataset.',
  }
}

/** Every route the prerenderer emits, given the dataset. */
export function allRoutes(dataset: Dataset): string[] {
  const routes = Object.keys(STATIC_META)
  for (const m of dataset.models) routes.push(`/models/${slugify(m.name)}`)
  // One page per measured model-on-GPU pair. Only pairs that were actually
  // benchmarked get a route: a page promising a number it does not have is
  // worse than no page.
  const pairs = new Set<string>()
  for (const result of dataset.results) {
    const modelSlug = slugify(result.model?.name ?? '')
    const gpuSlug = slugify(result.system?.gpu ?? '')
    if (modelSlug && gpuSlug) pairs.add(`/models/${modelSlug}/on/${gpuSlug}`)
  }
  routes.push(...pairs)
  for (const h of dataset.hardware) routes.push(`/hardware/${h.fingerprint}`)
  for (const r of dataset.runtimes) routes.push(`/runtimes/${r.name}`)
  for (const r of dataset.results) routes.push(`/results/${r.run_id}`)
  return Array.from(new Set(routes))
}
