// Shared types mirroring the generated static dataset (web/public/data).

export interface SystemInfo {
  os?: string | null
  os_version?: string | null
  cpu?: string | null
  cpu_cores_physical?: number | null
  cpu_cores_logical?: number | null
  gpu?: string | null
  gpu_vram_mb?: number | null
  npu?: string | null
  ram_gb?: number | null
  platform_name?: string | null
}

export interface RuntimeBlock {
  name: string
  version?: string | null
  backend?: string | null
  device?: string | null
}

export interface ModelBlock {
  name: string
  format?: string | null
  quantization?: string | null
  parameters?: string | null
  checksum?: string | null
}

export interface Metrics {
  load_time_ms?: number | null
  ttft_ms?: number | null
  prompt_tokens_per_second?: number | null
  generation_tokens_per_second?: number | null
  total_latency_ms?: number | null
  p50_latency_ms?: number | null
  p95_latency_ms?: number | null
  peak_ram_mb?: number | null
  peak_vram_mb?: number | null
  avg_cpu_util_percent?: number | null
  avg_gpu_util_percent?: number | null
  max_temperature_c?: number | null
  average_power_watts?: number | null
  performance_per_watt?: number | null
}

export interface Reproducibility {
  prompt?: string
  max_tokens?: number
  temperature?: number
  seed?: number
  context_length?: number
  warmup_runs?: number
  iterations?: number
  command?: string
  python_version?: string
  power_profile?: string
}

export interface BenchmarkResultDoc {
  schema_version: string
  run_id: string
  timestamp?: string
  trust_state?: string | null
  system?: SystemInfo
  runtime?: RuntimeBlock
  model?: ModelBlock
  metrics?: Metrics
  reproducibility?: Reproducibility
  _file?: string
}

export interface HardwareEntry {
  fingerprint: string
  cpu?: string | null
  gpu?: string | null
  npu?: string | null
  os?: string | null
  ram_gb?: number | null
  result_ids: string[]
}

export interface RuntimeEntry {
  name: string
  versions: string[]
  device_options: string[]
  result_ids: string[]
}

export interface ModelEntry {
  name: string
  format?: string | null
  quantizations: string[]
  checksums: string[]
  result_ids: string[]
}

export interface LeaderboardRow {
  rank: number
  run_id: string
  runtime?: string | null
  model?: string | null
  cpu?: string | null
  gpu?: string | null
  value?: number | null
}

export interface LeaderboardViews {
  throughput: LeaderboardRow[]
  ttft: LeaderboardRow[]
  perf_watt: LeaderboardRow[]
}

export interface TrendPoint {
  timestamp?: string
  version?: string | null
  throughput?: number | null
  ttft_ms?: number | null
}

export interface DatasetIndex {
  schema_version: string
  results_count: number
  hardware_count: number
  runtime_count: number
  model_count: number
  source_dir: string
  note: string
}

export interface Dataset {
  index: DatasetIndex
  results: BenchmarkResultDoc[]
  hardware: HardwareEntry[]
  runtimes: RuntimeEntry[]
  models: ModelEntry[]
  leaderboard: LeaderboardViews
  trends: Record<string, TrendPoint[]>
}