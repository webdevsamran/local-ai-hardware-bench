/**
 * One dataset fixture, shared by the tests that need one.
 *
 * It was written inline in `App.test.tsx` and is now imported by the
 * hydration tests too. Two copies would diverge on the first schema change,
 * and a hydration test running against a stale shape would pass while the
 * real server and client disagreed -- which is precisely the failure it
 * exists to catch.
 *
 * The shape mirrors the generated files in `web/public/data/`.
 */

export const indexDoc = {
  schema_version: '1.0',
  results_count: 1,
  hardware_count: 1,
  runtime_count: 1,
  model_count: 1,
  source_dir: 'results/published',
  note: 'test',
}
export const resultDoc = {
  schema_version: '1.0',
  run_id: 'test-run-1',
  timestamp: '2026-01-01T00:00:00Z',
  system: { os: 'TestOS', cpu: 'Test CPU', gpu: null },
  runtime: { name: 'ollama', version: '1.0', device: 'cpu' },
  model: { name: 'm', format: 'gguf' },
  metrics: { generation_tokens_per_second: 10.0, ttft_ms: 100.0 },
}
export const dataset = {
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
  comparability: {
    strict: ['model.name', 'runtime.name'],
    conditional: ['runtime.version'],
    required_present: ['model.name', 'runtime.name'],
    insufficient_metadata_reason: 'insufficient_metadata',
    reference_cases: [],
    empty_case: { classification: 'NOT_COMPARABLE', machine_reasons: ['insufficient_metadata'] },
  },
  pareto: {},
  recommend: { note: '', reference_cases: [] },
  privacy: { patterns: [], reference_cases: [], note: '' },
  cliff: { curves: [], note: '' },
  kvcache: {
    note: 'Quantizing the KV cache is a memory setting, not a speed one.',
    studies: [
      {
        source: 'sweep-test.json',
        runtime: 'llama.cpp',
        model: 'Test Model',
        model_key: 'test-model',
        gpu: 'Test GPU',
        gpu_vram_mb: 16384,
        timestamp: '2026-09-11T00:00:00Z',
        report: {
          context_length: 32768,
          geometry: { block_count: 24, head_count_kv: 2, head_dim: 64 },
          baseline: {
            cache_type_k: 'f16',
            cache_type_v: 'f16',
            peak_vram_mb: 1022,
            generation_tokens_per_second: 382.3,
            kv_cache_mb: 384,
          },
          configurations: [
            {
              cache_type_k: 'q4_0',
              cache_type_v: 'q4_0',
              is_baseline: false,
              kv_cache_mb: 108,
              kv_cache_saved_mb: 276,
              kv_cache_saved_percent: 71.9,
              peak_vram_mb: 748,
              measured_vram_saved_mb: 274,
              generation_tokens_per_second: 382.4,
              throughput_change_percent: 0,
              throughput_distinguishable: false,
            },
            {
              cache_type_k: 'q8_0',
              cache_type_v: 'f16',
              is_baseline: false,
              kv_cache_mb: 294,
              kv_cache_saved_mb: 90,
              kv_cache_saved_percent: 23.4,
              peak_vram_mb: 1858,
              measured_vram_saved_mb: -836,
              generation_tokens_per_second: 358.4,
              throughput_change_percent: -6.3,
              throughput_distinguishable: false,
              costs_more_than_baseline: true,
              measurement_note: 'used more than the baseline',
            },
            {
              cache_type_k: 'f16',
              cache_type_v: 'f16',
              is_baseline: true,
              kv_cache_mb: 384,
              peak_vram_mb: 1022,
              generation_tokens_per_second: 382.3,
            },
          ],
          framing: 'memory before throughput',
          unresolved: null,
        },
      },
    ],
  },
}
