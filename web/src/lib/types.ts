// Shared types mirroring the generated static dataset (web/public/data).

import type { PrivacyRules } from './privacy'

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
  /**
   * Spread of the headline metric across iterations. A mean without these is
   * a number that cannot be argued with; published results carry them so a
   * reader can see whether two figures are actually different.
   */
  gen_tps_ci95?: [number, number] | null
  generation_tps_cv?: number | null
  generation_tps_stddev?: number | null
  /** Inter-token latency as a distribution: a mean cannot show a stall. */
  itl_p50_ms?: number | null
  itl_p90_ms?: number | null
  itl_p99_ms?: number | null
  itl_max_ms?: number | null
}

/** Machine load sampled immediately before a run began. */
export interface MachineContention {
  cpu_percent?: number | null
  /** True when load was measured and exceeded the threshold. Null = unknown. */
  busy?: boolean | null
  threshold_percent?: number | null
  reason?: string | null
}

/** Derived energy figures, with what bounds their precision. */
export interface EnergyBlock {
  energy_joules_per_token?: number | null
  incremental_power_watts?: number | null
  gross_average_power_watts?: number | null
  idle_baseline_power_watts?: number | null
  idle_power_spread_watts?: number | null
  incremental_share_of_gross?: number | null
  /** False when the figure is mostly baseline, or inside its noise. */
  incremental_is_robust?: boolean | null
  caveat?: string | null
  telemetry_source?: string | null
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
  machine_contention?: MachineContention | null
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
  /** Derived energy figures; see EnergyBlock for what bounds their precision. */
  energy?: EnergyBlock | null
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
  /** Rank *within* the comparison group, not across the dataset. */
  rank: number
  /** Index of the comparison group this result belongs to. */
  group: number
  /** What the members of that group share (same model, runtime, workload). */
  group_label: string
  /** How many results are in the group; 1 means nothing to compare against. */
  group_size: number
  run_id: string
  runtime?: string | null
  model?: string | null
  cpu?: string | null
  gpu?: string | null
  value?: number | null
  /** Unit for performance-per-watt rows: tok/s/W and inf/s/W are different. */
  unit?: string | null
  /** Filterable dimensions. */
  vram_mb?: number | null
  vram_tier?: string | null
  quantization?: string | null
  device?: string | null
  trust?: string | null
  /** 95% confidence interval for `value`, when the metric measured one. */
  ci95?: [number, number] | null
  /** Coefficient of variation across iterations, when measured. */
  cv?: number | null
  /**
   * True when this row's interval overlaps rank 1's, so the two are not
   * distinguishable at this sample size and the rank gap is not a real one.
   * Null when the metric carries no interval: unknown, not "distinguishable".
   */
  indistinguishable_from_rank_1?: boolean | null
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

/** Reference case generated by the canonical Python fit estimator. */
export interface FitReferenceCase {
  parameters: string | null
  quantization: string | null
  available_vram_mb: number | null
  available_ram_mb: number | null
  context_tokens: number
  expected: {
    estimated_weights_gb: number | null
    estimated_total_gb: number | null
    fits: boolean | null
    fit_target?: string | null
    reason: string
  }
}

/**
 * Constants for the browser-side fit estimator, generated from
 * `aihwbench/analysis/fit.py` so the two implementations cannot drift.
 */
export interface FitConstants {
  bits_per_weight: Record<string, number>
  overhead_factor: number
  note: string
  reference_cases: FitReferenceCase[]
}

/** Verdict computed by the canonical Python classifier, for parity tests. */
export interface ComparabilityReferenceCase {
  a: string
  b: string
  classification: string
  machine_reasons: string[]
}

/**
 * The comparison-safety rule tables, generated from
 * `aihwbench/comparability.py` so the browser reaches the same verdict as
 * the CLI for any pair a reader picks.
 */
export interface ComparabilityRules {
  strict: string[]
  conditional: string[]
  required_present: string[]
  insufficient_metadata_reason: string
  reference_cases: ComparabilityReferenceCase[]
  empty_case: { classification: string; machine_reasons: string[] }
}

export interface ParetoPoint {
  run_id: string
  runtime?: string | null
  model?: string | null
  gpu?: string | null
  x: number
  y: number
  optimal: boolean
}

export interface ParetoView {
  x_metric: string
  y_metric: string
  x_higher_is_better: boolean
  y_higher_is_better: boolean
  points: ParetoPoint[]
  excluded_missing_metrics: number
}

export interface Dataset {
  index: DatasetIndex
  results: BenchmarkResultDoc[]
  hardware: HardwareEntry[]
  runtimes: RuntimeEntry[]
  models: ModelEntry[]
  leaderboard: LeaderboardViews
  trends: Record<string, TrendPoint[]>
  constants: FitConstants
  comparability: ComparabilityRules
  pareto: Record<string, ParetoView>
  recommend: { note: string; reference_cases: unknown[] }
  /** The privacy scanner's patterns, generated from aihwbench/sanitize.py. */
  privacy: PrivacyRules
  /** Measured offload sweeps with the cliff analysis applied. */
  cliff: OffloadCliffData
}

/** One measured point on an offload sweep. */
export interface OffloadCliffPoint {
  gpu_layers: number
  tokens_per_second: number | null
  ci95?: [number, number] | null
  cv?: number | null
  peak_vram_mb?: number | null
}

export interface OffloadCliffAnalysis {
  axis: string
  points: number
  excluded_missing_data: number
  cliff_detected: boolean | null
  threshold?: number
  largest_drop_fraction?: number
  cliff_between_layers?: [number, number] | null
  best_layers?: number
  best_tokens_per_second?: number
  /**
   * Settings the best one cannot be told apart from. Non-empty means the
   * "fastest" is a sort order rather than a measured lead.
   */
  best_is_tied_with?: number[]
  tie_basis?: string | null
  reason?: string
}

export interface OffloadCliffCurve {
  source: string
  runtime?: string | null
  model?: string | null
  gpu?: string | null
  gpu_vram_mb?: number | null
  cpu?: string | null
  timestamp?: string | null
  analysis: OffloadCliffAnalysis
  points: OffloadCliffPoint[]
}

export interface OffloadCliffData {
  curves: OffloadCliffCurve[]
  note: string
}