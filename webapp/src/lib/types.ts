// JSON contract mirrors webapp_export.py exactly.

export interface Meta {
  generated_at: string;
  model: string;
  universe_size: number;
  n_sectors: number;
  n_cross_sections: number;
  rebalance_freq?: string;
  selection_index?: string | null;
  n_selection?: number | null;
  n_quarterly_cross_sections?: number | null;
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
  index_counts?: Record<string, number>;
  use_estimate_factors: boolean;
  diagnostics: Diagnostics;
  exclusions_summary?: { n_labels_excluded: number; n_tickers: number; reasons: Record<string, number> };
  mc_portfolio_size?: number;
  mc_n_trials?: number;
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
  index_name?: string | null;
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
  ticker: string; gics_sector: string; index_name?: string | null; torpedo_score: number | null;
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
  per_decile_mean: { decile: number; mean_rel_ret: number; median_rel_ret: number | null; mean_rel_ret_w: number | null; n: number }[];
  spread_mean: number | null; spread_tstat: number | null; monotonicity_rho: number | null;
  spread_series: { date: string; spread: number }[];
}

export interface CalibrationRow {
  score_q: number;
  mean_rel_ret: number | null;
  se: number | null;
  t_stat: number | null;
  median_rel_ret: number | null;
  mean_rel_ret_w: number | null;
  p_underperform: number | null;
  p_underperform_se: number | null;
  mean_score: number | null;
  n_dates: number;
  n_obs: number;
}

export interface EventStudyRow {
  cohort: "all" | "entrant";
  k: number;
  mean_rel_ret: number | null;
  se: number | null;
  mean_rel_ret_w: number | null;
  cum_mean: number | null;
  n: number;
}

export interface EraRow { date: string; avg_factors: number; era: string; }
export interface EraICRow { era: string; mean_ic: number | null; t_stat: number | null; ir: number | null; n_periods: number; }
export interface YearlyICRow { year: number; mean_ic: number | null; n_periods: number; }
export interface Promotion { mean_diff: number | null; t_stat: number | null; n_periods: number; promote: boolean; }

export interface StressWindowRow {
  window: string; start: string; end: string;
  mean_ic: number | null; n_periods: number;
  spread_mean: number | null; bench_return: number | null;
}

export interface HorizonICRow {
  series: string; kind: "composite" | "family" | "factor";
  horizon: string; months: number;
  mean_ic: number | null; t_stat: number | null; se: number | null;
  ir: number | null; n_periods: number;
}

export interface Validation {
  ic: Record<string, ICBlock>;
  deciles: Record<string, DecileBlock>;
  calibration: CalibrationRow[];
  model_comparison: { model: string; score_col: string; mean_ic: number; t_stat: number; ir: number; hit_rate: number; n_periods: number }[];
  promotion: Promotion | null;
  event_study: EventStudyRow[];
  eras: EraRow[];
  era_ic: EraICRow[];
  yearly_ic: YearlyICRow[];
  family_ic_rolling: Record<string, string | number | null>[];
  stress_windows: StressWindowRow[];
  horizon_term_structure: HorizonICRow[];
  label_winsor_pct: number;
  era_min_avg_factors: number;
}

export interface BacktestSleeve {
  name: string;
  metrics: Record<string, number | null>;
  curve: { date: string; strategy: number; benchmark: number | null }[];
  returns: { date: string; ret: number }[];
  turnover: { date: string; turnover: number }[];
}
export interface Backtest {
  sleeves: Record<string, BacktestSleeve>;
  segments: {
    by_year: Record<string, number | null>[];
    by_regime: Record<string, number | string | null>[];
  };
}

export interface MCTier {
  label: string;
  cagr: { p5: number; p25: number; p50: number; p75: number; p95: number; mean: number };
  prob_beat_full_median: number | null;
  trial_cagrs: number[];
  equity_bands: Record<string, number[]>;
}
export interface MCSim {
  dates?: string[];
  n_names?: number;
  n_trials?: number;
  tiers?: Record<string, MCTier>;
}

export interface Exclusions {
  n_labels_excluded: number;
  n_tickers: number;
  reasons: Record<string, number>;
  rows: { date: string; ticker: string; horizon_q: number; reason: string; value: number | null }[];
}

export interface DrilldownFactor {
  raw: number | null;
  z: number | null;
  pct: number | null;      // within sector percentile of the aligned z (100 = worst red flag)
  prev_z: number | null;
}
export interface DrilldownName {
  sector: string;
  index_name: string;
  score: number | null;
  decile: number | null;
  prev_score: number | null;
  prev_decile: number | null;
  n_factors_used: number;
  fund_as_of: string | null;
  torpedo_pct: number | null;
  torpedo_tier: string | null;
  short_pct_float: number | null;
  factors: Record<string, DrilldownFactor | null>;
}
export interface Drilldown {
  as_of: string;
  prev_date: string | null;
  factor_order: string[];
  names: Record<string, DrilldownName>;
}

export interface OverrideRow {
  date: string;
  ticker: string;
  analyst: string;
  direction: "less_risky" | "more_risky";
  reason_code: string;
  factor: string;
  note: string;
  expires: string;
}
export interface OverrideScoreboard {
  n_overrides: number;
  n_scored_obs: number;
  analyst_hit_rate: number | null;
  model_hit_rate: number | null;
  by_reason: { reason_code: string; n_obs: number; analyst_hit_rate: number; avg_rel_ret: number }[];
  rows: { ticker: string; analyst: string; direction: string; reason_code: string; quarter: string; rel_ret: number; analyst_correct: boolean }[];
}
export interface Overrides {
  active: OverrideRow[];
  scoreboard: OverrideScoreboard | Record<string, never>;
  reason_codes: string[];
}

export interface Transitions {
  n_deciles: number;
  n_date_pairs: number;
  counts: number[][];
  row_prob: number[][];
  new_flagged: { ticker: string; sector: string; decile: number; prev_decile: number | null }[];
  exited: { ticker: string; sector: string; decile: number; prev_decile: number }[];
  latest_date: string | null;
  prev_date: string | null;
}
