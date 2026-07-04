// JSON contract mirrors webapp_export.py exactly.

export interface Meta {
  generated_at: string;
  model: string;
  universe_size: number;
  n_sectors: number;
  n_cross_sections: number;
  panel_rows: number;
  n_delisted_carried: number;
  horizon_q: number;
  horizons_available: number[];
  benchmark: string;
  source: string;
  cost_bps: number;
  neutralize_method: string;
  n_factors: number;
  factor_groups: Record<string, string>;
  learned_weights_enabled: boolean;
  default_score: string;
  membership_point_in_time: boolean;
  use_estimate_factors: boolean;
  diagnostics: Diagnostics;
  sector_colors: Record<string, string>;
  torpedo_tier_colors: Record<string, string>;
  torpedo_tier_order: string[];
  n_torpedo_features: number;
}

export interface Diagnostics {
  all_passed: boolean;
  placebo: { real_ic: number; real_t: number; placebo_ic_mean: number; placebo_ic_std: number; tolerance: number; passed: boolean };
  lookahead: { passed: boolean; no_label_in_features: { n_features: number; leak_columns: string[]; passed: boolean }; price_factor_truncation?: { checked: number; mismatches: number; passed: boolean } };
  survivorship: { passed: boolean; delisting_carried: { delisted_carried: boolean; survivor_scored: boolean; terminal_return: number; passed: boolean }; membership: { real_point_in_time: boolean; note: string; passed: boolean } };
}

export interface ScoreRow {
  date: string;
  ticker: string;
  gics_sector: string;
  score: number | null;
  decile: number | null;
  n_factors_used: number;
  short_pct_float: number | null;
  sell_rank: number | null;
  torpedo_score?: number | null;
  torpedo_pct?: number | null;
  torpedo_tier?: string | null;
  [factorN: string]: number | string | null | undefined;
}

export interface TorpedoName {
  ticker: string; gics_sector: string; torpedo_score: number | null;
  torpedo_pct: number | null; torpedo_tier: string | null;
  decile: number | null; score: number | null; short_pct_float: number | null;
}
export interface Torpedo {
  names: TorpedoName[];
  tier_counts: { torpedo_tier: string; n: number }[];
  tier_colors: Record<string, string>;
  tier_order: string[];
}

export interface SectorDeciles {
  counts: { gics_sector: string; decile: number; n: number }[];
  worst_decile_names: Record<string, string[]>;
  n_deciles: number;
  sectors: string[];
}

export interface FactorICRow {
  factor: string; group: string; mean_ic: number | null; t_stat: number | null;
  ir: number | null; hit_rate: number | null; n_periods: number;
}
export interface FactorIC { horizon_q: number; factors: FactorICRow[]; }

export interface ICBlock {
  mean_ic: number | null; t_stat: number | null; ir: number | null;
  hit_rate: number | null; n_periods: number;
  series: { date: string; ic: number; n: number }[];
}
export interface DecileBlock {
  per_decile_mean: { decile: number; mean_rel_ret: number; n: number }[];
  spread_mean: number | null; spread_tstat: number | null; monotonicity_rho: number | null;
  spread_series: { date: string; spread: number }[];
}
export interface Validation {
  ic: Record<string, ICBlock>;
  deciles: Record<string, DecileBlock>;
  calibration: { score_q: number; mean_score: number; mean_rel_ret: number; n: number }[];
  model_comparison: { model: string; score_col: string; mean_ic: number; t_stat: number; ir: number; hit_rate: number; n_periods: number }[];
}

export interface BacktestSleeve {
  name: string;
  metrics: Record<string, number>;
  curve: { date: string; strategy: number; benchmark: number | null }[];
  returns: { date: string; ret: number }[];
  turnover: { date: string; turnover: number }[];
}
export type Backtest = Record<string, BacktestSleeve>;
