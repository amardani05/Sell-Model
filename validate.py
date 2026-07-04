"""Validation — the first class deliverable of this project.

A sell model is only worth anything if its score actually ranks forward
SECTOR RELATIVE returns out of sample. Everything here measures exactly that.

Sign convention (read once):
    The published score ranks expected UNDERPERFORMANCE (higher = sell). To keep
    the universal "positive IC = skill" convention, we report
        IC  =  - Spearman( score , forward_relative_return )
            =    Spearman( expected_outperformance , realized_relative_return )
    so a skillful model has POSITIVE IC, a decile spread that is POSITIVE
    (best decile minus worst decile relative return), and decile means that
    DECREASE monotonically as the sell decile rises. The placebo test (shuffle
    the score) must collapse IC to ~0 regardless of this sign.

Metrics:
  * per cross section IC time series;
  * Fama MacBeth mean IC with a Newey West (HAC, 5 lag) t stat + IR;
  * decile spread (best minus worst) per period and pooled, with t stat;
  * decile monotonicity (Spearman of decile index vs mean relative return);
  * a simple calibration table (mean realized relative return by score quantile).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
import statsmodels.api as sm

import config

logger = logging.getLogger(__name__)

NEWEY_WEST_LAGS: int = 5


def _hac_tstat(series: pd.Series) -> tuple[float, float, float]:
    """Mean, Newey West (HAC, 5 lag) t stat, and IR of a per period series."""
    x = series.dropna().astype(float)
    if len(x) < 3:
        return float(x.mean()) if len(x) else np.nan, np.nan, np.nan
    y = x.values
    X = np.ones((len(y), 1))
    model = sm.OLS(y, X).fit(cov_type="HAC", cov_kwds={"maxlags": NEWEY_WEST_LAGS})
    mean = float(model.params[0])
    tstat = float(model.params[0] / model.bse[0]) if model.bse[0] > 0 else np.nan
    ir = float(x.mean() / x.std(ddof=1)) if x.std(ddof=1) > 0 else np.nan
    return mean, tstat, ir


# =============================================================================
# Information Coefficient
# =============================================================================
def ic_time_series(panel: pd.DataFrame, score_col: str, horizon_q: int) -> pd.DataFrame:
    """Per date skill signed IC = -Spearman(score, fwd_rel_ret). Cols: date, ic, n."""
    label = f"fwd_rel_ret_{horizon_q}q"
    rows = []
    for t, g in panel.groupby("date"):
        d = g[[score_col, label]].dropna()
        if len(d) < config.MIN_NAMES_PER_SECTOR * 2:
            continue
        rho, _ = spearmanr(d[score_col], d[label])
        if np.isfinite(rho):
            rows.append({"date": pd.Timestamp(t), "ic": -float(rho), "n": len(d)})
    if not rows:
        return pd.DataFrame(columns=["date", "ic", "n"])
    return pd.DataFrame(rows).sort_values("date").reset_index(drop=True)


@dataclass
class ICSummary:
    horizon_q: int
    score_col: str
    mean_ic: float
    t_stat: float
    ir: float
    hit_rate: float           # fraction of cross sections with IC > 0
    n_periods: int
    series: pd.DataFrame = field(default_factory=pd.DataFrame)


def summarize_ic(panel: pd.DataFrame, score_col: str, horizon_q: int) -> ICSummary:
    ts = ic_time_series(panel, score_col, horizon_q)
    if ts.empty:
        return ICSummary(horizon_q, score_col, np.nan, np.nan, np.nan, np.nan, 0, ts)
    mean, t, ir = _hac_tstat(ts["ic"])
    hit = float((ts["ic"] > 0).mean())
    logger.info("IC[%s h=%dq]: mean=%.4f t=%.2f IR=%.2f hit=%.0f%% over %d periods",
                score_col, horizon_q, mean, t, ir, hit * 100, len(ts))
    return ICSummary(horizon_q, score_col, mean, t, ir, hit, len(ts), ts)


# =============================================================================
# Decile spread + monotonicity
# =============================================================================
@dataclass
class DecileSummary:
    horizon_q: int
    decile_col: str
    per_decile_mean: pd.DataFrame       # decile, mean_rel_ret, n
    spread_mean: float                  # best minus worst, pooled
    spread_tstat: float
    spread_series: pd.DataFrame         # date, spread
    monotonicity_rho: float             # Spearman(decile, mean_rel_ret); want < 0


def decile_analysis(panel: pd.DataFrame, decile_col: str, horizon_q: int) -> DecileSummary:
    label = f"fwd_rel_ret_{horizon_q}q"
    d = panel[[decile_col, label, "date"]].dropna()
    n = config.N_DECILES

    per = (d.groupby(decile_col)[label]
             .agg(["mean", "count"]).reset_index()
             .rename(columns={decile_col: "decile", "mean": "mean_rel_ret", "count": "n"}))

    # per date spread = mean(best decile==1) - mean(worst decile==n)
    rows = []
    for t, g in d.groupby("date"):
        best = g.loc[g[decile_col] == 1, label].mean()
        worst = g.loc[g[decile_col] == n, label].mean()
        if np.isfinite(best) and np.isfinite(worst):
            rows.append({"date": pd.Timestamp(t), "spread": best - worst})
    spread_series = (pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
                     if rows else pd.DataFrame(columns=["date", "spread"]))
    spread_mean, spread_t, _ = _hac_tstat(spread_series["spread"]) if not spread_series.empty else (np.nan, np.nan, np.nan)

    rho = np.nan
    if len(per) >= 3:
        rho, _ = spearmanr(per["decile"], per["mean_rel_ret"])

    logger.info("Decile[%s h=%dq]: spread(best worst)=%.4f t=%.2f monotonicity rho=%.2f",
                decile_col, horizon_q, spread_mean, spread_t, rho)
    return DecileSummary(horizon_q, decile_col, per, spread_mean, spread_t, spread_series, float(rho))


# =============================================================================
# Calibration
# =============================================================================
def calibration_table(panel: pd.DataFrame, score_col: str, horizon_q: int, q: int = 10) -> pd.DataFrame:
    """Mean realized relative return by pooled score quantile (sorted worst->best)."""
    label = f"fwd_rel_ret_{horizon_q}q"
    d = panel[[score_col, label]].dropna().copy()
    if len(d) < q * 2:
        return pd.DataFrame(columns=["score_q", "mean_score", "mean_rel_ret", "n"])
    d["score_q"] = pd.qcut(d[score_col].rank(method="first"), q, labels=False) + 1
    out = (d.groupby("score_q")
             .agg(mean_score=(score_col, "mean"), mean_rel_ret=(label, "mean"), n=(label, "size"))
             .reset_index())
    return out


# =============================================================================
# Per factor IC  (which factors actually carry the model)
# =============================================================================
def factor_ic_table(panel: pd.DataFrame, horizon_q: int) -> pd.DataFrame:
    """IC of each direction aligned sector neutral factor, on its own.

    Uses the ``<factor>__n`` column directly as a one factor score, so a positive
    IC means the factor's documented red flag direction is paying off in sample.
    """
    rows = []
    for f in config.active_factors():
        col = f"{f}__n"
        if col not in panel.columns or not panel[col].notna().any():
            continue
        s = summarize_ic(panel, col, horizon_q)
        rows.append({
            "factor": f, "group": config.FACTOR_GROUPS.get(f, "Other"),
            "mean_ic": s.mean_ic, "t_stat": s.t_stat, "ir": s.ir,
            "hit_rate": s.hit_rate, "n_periods": s.n_periods,
        })
    out = pd.DataFrame(rows)
    return out.sort_values("mean_ic", ascending=False).reset_index(drop=True) if not out.empty else out


# =============================================================================
# Baseline vs learned, head to head (OOS)
# =============================================================================
def compare_models(panel: pd.DataFrame, horizon_q: int) -> pd.DataFrame:
    """Side by side OOS IC for equal weight vs learned weight (if present)."""
    rows = []
    for col, name in [("score_ew", "equal_weight"), ("score_ml", "learned_weight")]:
        if col not in panel.columns or not panel[col].notna().any():
            continue
        s = summarize_ic(panel, col, horizon_q)
        rows.append({"model": name, "score_col": col, "mean_ic": s.mean_ic,
                     "t_stat": s.t_stat, "ir": s.ir, "hit_rate": s.hit_rate,
                     "n_periods": s.n_periods})
    return pd.DataFrame(rows)
