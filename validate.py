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
  * Fama MacBeth mean IC with a Newey West (HAC) t stat + IR — lags scale with
    the label overlap (horizon − 1 quarters, floored at 1);
  * decile spread (best minus worst) per period and pooled, with t stat;
  * decile monotonicity (Spearman of decile index vs mean relative return);
  * a Fama MacBeth calibration table: score quantiles are cut WITHIN each date,
    then the per bin stats are averaged across dates with standard errors —
    means, medians, winsorized means, and P(underperform sector);
  * a decile 10 event study (what happens 0..K quarters after a name is flagged);
  * coverage era splits (price only era vs full factor era) so a 2 factor
    history is never presented as evidence about the 15 factor composite;
  * a paired IC test that decides learned vs baseline promotion.
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


def _nw_lags_months(months: int) -> int:
    """Newey West lag choice for a label ``months`` long, floored at 1.

    Adjacent observations share (label length − 1) SAMPLING periods of the same
    forward window: months − 1 on the monthly grid, months/3 − 1 on the
    quarterly grid. That overlap is exactly the autocorrelation HAC must
    absorb — this is what makes the overlapping grid statistically legitimate
    rather than multiple counting the same window.
    """
    per_q = config.PERIODS_PER_QUARTER.get(config.REBALANCE_FREQ, 1)
    periods = int(round(months * per_q / 3))
    return max(1, periods - 1)


def _nw_lags(horizon_q: int) -> int:
    """Newey West lags for an ``horizon_q`` quarter label (see _nw_lags_months)."""
    return _nw_lags_months(3 * int(horizon_q))


def _hac_tstat(series: pd.Series, lags: int = 1) -> tuple[float, float, float]:
    """Mean, Newey West (HAC, ``lags``) t stat, and IR of a per period series."""
    x = series.dropna().astype(float)
    if len(x) < 3:
        return float(x.mean()) if len(x) else np.nan, np.nan, np.nan
    y = x.values
    X = np.ones((len(y), 1))
    model = sm.OLS(y, X).fit(cov_type="HAC", cov_kwds={"maxlags": max(1, lags)})
    mean = float(model.params[0])
    tstat = float(model.params[0] / model.bse[0]) if model.bse[0] > 0 else np.nan
    ir = float(x.mean() / x.std(ddof=1)) if x.std(ddof=1) > 0 else np.nan
    return mean, tstat, ir


def _winsorize_series(s: pd.Series, pct: float = config.LABEL_WINSOR_PCT) -> pd.Series:
    """Clip a label series at [pct, 1 − pct] quantiles (display statistics only)."""
    v = s.dropna()
    if len(v) < 10 or pct <= 0:
        return s
    return s.clip(v.quantile(pct), v.quantile(1 - pct))


# =============================================================================
# Information Coefficient
# =============================================================================
def ic_time_series(panel: pd.DataFrame, score_col: str, horizon_q: int) -> pd.DataFrame:
    """Per date skill signed IC = -Spearman(score, fwd_rel_ret). Cols: date, ic, n."""
    return ic_series_for_label(panel, score_col, f"fwd_rel_ret_{horizon_q}q")


def ic_series_for_label(panel: pd.DataFrame, score_col: str, label: str) -> pd.DataFrame:
    """ic_time_series against an arbitrary relative return label column."""
    if score_col not in panel.columns or label not in panel.columns:
        return pd.DataFrame(columns=["date", "ic", "n"])
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
    return summarize_ic_for_label(panel, score_col, f"{horizon_q}q", 3 * horizon_q)


def summarize_ic_for_label(panel: pd.DataFrame, score_col: str,
                           suffix: str, months: int) -> ICSummary:
    """summarize_ic for any label horizon suffix ("1m"/"1q"/"2q"/"4q")."""
    ts = ic_series_for_label(panel, score_col, f"fwd_rel_ret_{suffix}")
    if ts.empty:
        return ICSummary(months, score_col, np.nan, np.nan, np.nan, np.nan, 0, ts)
    mean, t, ir = _hac_tstat(ts["ic"], lags=_nw_lags_months(months))
    hit = float((ts["ic"] > 0).mean())
    logger.info("IC[%s h=%s]: mean=%.4f t=%.2f IR=%.2f hit=%.0f%% over %d periods",
                score_col, suffix, mean, t, ir, hit * 100, len(ts))
    return ICSummary(months, score_col, mean, t, ir, hit, len(ts), ts)


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
    return decile_analysis_for_label(panel, decile_col, f"{horizon_q}q", 3 * horizon_q)


def decile_analysis_for_label(panel: pd.DataFrame, decile_col: str,
                              suffix: str, months: int) -> DecileSummary:
    """decile_analysis for any label horizon suffix ("1m"/"1q"/"2q"/"4q")."""
    label = f"fwd_rel_ret_{suffix}"
    if label not in panel.columns:
        empty = pd.DataFrame(columns=["decile", "mean_rel_ret", "median_rel_ret",
                                      "mean_rel_ret_w", "n"])
        return DecileSummary(months, decile_col, empty, np.nan, np.nan,
                             pd.DataFrame(columns=["date", "spread"]), np.nan)
    d = panel[[decile_col, label, "date"]].dropna().copy()
    n = config.N_DECILES

    # Display honesty: relative returns are right skewed, so a raw mean can be
    # carried by one lottery quarter. Report median + winsorized mean alongside.
    d["_w"] = _winsorize_series(d[label])
    per = (d.groupby(decile_col)
             .agg(mean_rel_ret=(label, "mean"), median_rel_ret=(label, "median"),
                  mean_rel_ret_w=("_w", "mean"), n=(label, "size"))
             .reset_index()
             .rename(columns={decile_col: "decile"}))

    # per date spread = mean(best decile==1) - mean(worst decile==n)
    rows = []
    for t, g in d.groupby("date"):
        best = g.loc[g[decile_col] == 1, label].mean()
        worst = g.loc[g[decile_col] == n, label].mean()
        if np.isfinite(best) and np.isfinite(worst):
            rows.append({"date": pd.Timestamp(t), "spread": best - worst})
    spread_series = (pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
                     if rows else pd.DataFrame(columns=["date", "spread"]))
    spread_mean, spread_t, _ = (_hac_tstat(spread_series["spread"],
                                           lags=_nw_lags_months(months))
                                if not spread_series.empty else (np.nan, np.nan, np.nan))

    rho = np.nan
    if len(per) >= 3:
        rho, _ = spearmanr(per["decile"], per["mean_rel_ret"])

    logger.info("Decile[%s h=%s]: spread(best worst)=%.4f t=%.2f monotonicity rho=%.2f",
                decile_col, suffix, spread_mean, spread_t, rho)
    return DecileSummary(months, decile_col, per, spread_mean, spread_t, spread_series, float(rho))


# =============================================================================
# Calibration (Fama MacBeth: bin WITHIN each date, then average across dates)
# =============================================================================
def calibration_fm(panel: pd.DataFrame, score_col: str, horizon_q: int, q: int = 10) -> pd.DataFrame:
    """Score quantile response curve, computed the Fama MacBeth way.

    The old pooled version cut quantiles across ALL dates at once, so a stock's
    bin depended on when it was scored and one hot quarter could bleed across
    bins (a single spliced return once made bin 4 the "best"). Here quantiles
    are cut within each date; per bin statistics are then averaged across dates
    with standard errors, and skew robust companions are reported:

      mean_rel_ret / se / t_stat   across date average of per date bin means
      median_rel_ret               across date average of per date bin medians
      mean_rel_ret_w               same but labels winsorized within date first
      p_underperform / _se         fraction of names below their sector median
      mean_score                   average score per bin (x axis sanity)
      n_dates / n_obs              sample sizes
    """
    label = f"fwd_rel_ret_{horizon_q}q"
    d = panel[["date", score_col, label]].dropna()
    per_date_rows: list[pd.DataFrame] = []
    for t, g in d.groupby("date"):
        if len(g) < q * 2:
            continue
        g = g.copy()
        g["score_q"] = pd.qcut(g[score_col].rank(method="first"), q, labels=False) + 1
        g["_w"] = _winsorize_series(g[label])
        agg = g.groupby("score_q").agg(
            mean_rel_ret=(label, "mean"),
            median_rel_ret=(label, "median"),
            mean_rel_ret_w=("_w", "mean"),
            p_underperform=(label, lambda s: float((s < 0).mean())),
            mean_score=(score_col, "mean"),
            n_obs=(label, "size"),
        )
        per_date_rows.append(agg)
    if not per_date_rows:
        return pd.DataFrame(columns=["score_q", "mean_rel_ret", "se", "t_stat",
                                     "median_rel_ret", "mean_rel_ret_w",
                                     "p_underperform", "p_underperform_se",
                                     "mean_score", "n_dates", "n_obs"])
    stacked = pd.concat(per_date_rows, keys=range(len(per_date_rows)))
    gb = stacked.groupby(level="score_q")
    n_dates = gb.size()
    out = pd.DataFrame({
        "mean_rel_ret": gb["mean_rel_ret"].mean(),
        "se": gb["mean_rel_ret"].std(ddof=1) / np.sqrt(n_dates),
        "median_rel_ret": gb["median_rel_ret"].mean(),
        "mean_rel_ret_w": gb["mean_rel_ret_w"].mean(),
        "p_underperform": gb["p_underperform"].mean(),
        "p_underperform_se": gb["p_underperform"].std(ddof=1) / np.sqrt(n_dates),
        "mean_score": gb["mean_score"].mean(),
        "n_dates": n_dates,
        "n_obs": gb["n_obs"].sum(),
    }).reset_index()
    out["t_stat"] = out["mean_rel_ret"] / out["se"]
    return out


# =============================================================================
# Decile 10 event study — what happens AFTER a name is flagged
# =============================================================================
def decile_event_study(panel: pd.DataFrame, decile_col: str,
                       max_k: int = 4) -> pd.DataFrame:
    """Average sector relative return path 0..max_k−1 quarters after flagging.

    Every (ticker, date) sitting in the worst decile is an event. For each
    event time offset k the name's 1 quarter forward relative return at date
    t+k is collected (whether or not it is still flagged then — the question is
    "what happened after the flag", not "while flagged"). Reports, per k, the
    across event mean, standard error, winsorized mean, sample size, and the
    running cumulative sum of the means — the Piper style "decile 10 keeps
    underperforming" curve. ``cohort='entrant'`` rows restrict to names newly
    flagged at t (not flagged at t−1); ``cohort='all'`` is every flagged row.
    """
    label = "fwd_rel_ret_1q"
    n = config.N_DECILES
    dates = sorted(panel["date"].unique())
    date_pos = {d: i for i, d in enumerate(dates)}
    rel = panel.pivot_table(index="date", columns="ticker", values=label, aggfunc="first")
    rel = rel.reindex(dates)
    dec = panel.pivot_table(index="date", columns="ticker", values=decile_col, aggfunc="first")
    dec = dec.reindex(dates)

    col_pos = {tk: i for i, tk in enumerate(rel.columns)}
    rows = []
    for cohort in ("all", "entrant"):
        flagged = dec == n
        if cohort == "entrant":
            prev = dec.shift(1)
            flagged = flagged & prev.notna() & (prev != n)
        # stack the flag matrix into (date, ticker) event pairs
        ev = flagged.stack()
        ev = ev[ev]
        cum = 0.0
        for k in range(max_k):
            vals = []
            for (t, tk) in ev.index:
                i = date_pos[t] + k
                j = col_pos.get(tk)
                if i < len(dates) and j is not None:
                    v = rel.iat[i, j]
                    if pd.notna(v):
                        vals.append(v)
            if not vals:
                rows.append({"cohort": cohort, "k": k, "mean_rel_ret": np.nan, "se": np.nan,
                             "mean_rel_ret_w": np.nan, "cum_mean": np.nan, "n": 0})
                continue
            s = pd.Series(vals)
            m = float(s.mean())
            cum += m
            rows.append({
                "cohort": cohort, "k": k,
                "mean_rel_ret": m,
                "se": float(s.std(ddof=1) / np.sqrt(len(s))) if len(s) > 1 else np.nan,
                "mean_rel_ret_w": float(_winsorize_series(s).mean()),
                "cum_mean": cum,
                "n": int(len(s)),
            })
    out = pd.DataFrame(rows)
    for cohort in ("all", "entrant"):
        sub = out[out["cohort"] == cohort]
        if not sub.empty and sub["n"].sum() > 0:
            logger.info("Event study[%s]: cum %d q after flag = %+.4f (n at k=0: %d)",
                        cohort, max_k, sub["cum_mean"].iloc[-1], int(sub["n"].iloc[0]))
    return out


# =============================================================================
# Coverage eras — never pass a 2 factor history off as the 15 factor model
# =============================================================================
def coverage_eras(panel: pd.DataFrame) -> pd.DataFrame:
    """Per date average factor coverage + era label.

    Requires ``n_factors_used`` (added by the equal weight scorer). Dates whose
    average coverage is below ``config.ERA_MIN_AVG_FACTORS`` are the
    "price only" era: cross sections effectively scored by momentum + reversal
    alone because yfinance fundamentals do not reach back that far.
    """
    if "n_factors_used" not in panel.columns:
        return pd.DataFrame(columns=["date", "avg_factors", "era"])
    cov = panel.groupby("date")["n_factors_used"].mean().reset_index()
    cov.columns = ["date", "avg_factors"]
    cov["era"] = np.where(cov["avg_factors"] >= config.ERA_MIN_AVG_FACTORS,
                          "full factor", "price only")
    return cov


def ic_summary_by_era(panel: pd.DataFrame, score_col: str, horizon_q: int,
                      eras: pd.DataFrame) -> pd.DataFrame:
    """Mean IC / t / IR / n per coverage era (the honest headline split)."""
    ts = ic_time_series(panel, score_col, horizon_q)
    if ts.empty or eras.empty:
        return pd.DataFrame(columns=["era", "mean_ic", "t_stat", "ir", "n_periods"])
    era_of = dict(zip(pd.to_datetime(eras["date"]), eras["era"]))
    ts = ts.copy()
    ts["era"] = ts["date"].map(era_of)
    rows = []
    for era, g in ts.groupby("era"):
        mean, t, ir = _hac_tstat(g["ic"], lags=_nw_lags(horizon_q))
        rows.append({"era": era, "mean_ic": mean, "t_stat": t, "ir": ir,
                     "n_periods": int(len(g))})
    return pd.DataFrame(rows).sort_values("era").reset_index(drop=True)


def ic_by_year(panel: pd.DataFrame, score_col: str, horizon_q: int) -> pd.DataFrame:
    """Calendar year segmentation of the IC series (each year stands alone)."""
    ts = ic_time_series(panel, score_col, horizon_q)
    if ts.empty:
        return pd.DataFrame(columns=["year", "mean_ic", "n_periods"])
    ts["year"] = ts["date"].dt.year
    out = (ts.groupby("year")["ic"].agg(["mean", "count"]).reset_index()
             .rename(columns={"mean": "mean_ic", "count": "n_periods"}))
    return out


# =============================================================================
# "What broke, and when" — family level forensics
# =============================================================================
def family_ic_rolling(panel: pd.DataFrame, horizon_q: int, window: int = 12) -> pd.DataFrame:
    """Rolling mean IC of each factor FAMILY's sub score, per date.

    The composite can net to zero while its families are strongly nonzero in
    opposite directions (exactly what the 2011-2026 history showed: valuation
    flags positive, quality/accruals inverted). This series answers the
    diagnostic question directly: WHICH family broke, and WHEN — a regime
    chart, not a single pooled number. ``window`` is in cross sections
    (12 monthly observations = a one year lens).
    """
    fam_cols = [c for c in panel.columns if c.startswith("fam_") and c.endswith("__score")]
    frames = {}
    for c in fam_cols:
        label = c[len("fam_"):-len("__score")].replace("_", " ").title()
        ts = ic_time_series(panel, c, horizon_q)
        if ts.empty:
            continue
        frames[label] = ts.set_index("date")["ic"].rolling(window, min_periods=max(3, window // 2)).mean()
    if not frames:
        return pd.DataFrame(columns=["date"])
    out = pd.DataFrame(frames).reset_index().rename(columns={"index": "date"})
    return out


def stress_window_table(panel: pd.DataFrame, score_col: str, decile_col: str,
                        horizon_q: int,
                        benchmark_px: pd.Series | None = None) -> pd.DataFrame:
    """Validation stats inside each named disaster window (config.STRESS_WINDOWS).

    A model that averages to zero can still be strongly wrong in exactly the
    periods that hurt most — or genuinely protective there. Each row reports
    the episode's mean IC, decile spread, sample size, and the benchmark's
    move for context. Labels are forward looking FROM each date, so a window's
    row describes flags raised DURING the episode.
    """
    ic_ts = ic_time_series(panel, score_col, horizon_q).set_index("date")["ic"]
    label = f"fwd_rel_ret_{horizon_q}q"
    d = panel[[decile_col, label, "date"]].dropna()
    n_dec = config.N_DECILES

    rows = []
    for name, start, end in config.STRESS_WINDOWS:
        s, e = pd.Timestamp(start), pd.Timestamp(end)
        ic_w = ic_ts[(ic_ts.index >= s) & (ic_ts.index <= e)]
        w = d[(d["date"] >= s) & (d["date"] <= e)]
        spread = np.nan
        if not w.empty:
            per = w.groupby("date").apply(
                lambda g: g.loc[g[decile_col] == 1, label].mean()
                          - g.loc[g[decile_col] == n_dec, label].mean())
            spread = float(per.mean()) if len(per) else np.nan
        bench_ret = np.nan
        if benchmark_px is not None and len(benchmark_px):
            bpx = benchmark_px[(benchmark_px.index >= s) & (benchmark_px.index <= e)].dropna()
            if len(bpx) > 1:
                bench_ret = float(bpx.iloc[-1] / bpx.iloc[0] - 1.0)
        rows.append({
            "window": name, "start": start, "end": end,
            "mean_ic": float(ic_w.mean()) if len(ic_w) else np.nan,
            "n_periods": int(len(ic_w)),
            "spread_mean": spread,
            "bench_return": bench_ret,
        })
    return pd.DataFrame(rows)


def horizon_term_structure(panel: pd.DataFrame) -> pd.DataFrame:
    """IC of every family / composite / factor at each diagnostic horizon.

    The "IC decay curve" (roadmap 1.5): each series' Fama MacBeth mean IC is
    measured against the sector relative forward return at every
    ``config.TERM_STRUCTURE_HORIZONS`` label present in the panel. Families
    are expected to differ in SPEED — short term reversal pays within a month
    and is gone (Jegadeesh 1990), while value / quality / accruals build over
    quarters (Sloan 1996 accruals is an annual horizon effect) — so this
    decides whether a family that looks broken at 1Q is mis horizoned (turns
    positive further out) or genuinely inverted (negative everywhere). Newey
    West lags scale with each label's overlap on the sampling grid.

    Read the output as SHAPES, not stars: ~27 series x 4 horizons is 100+
    t stats, so ~5 clear |t| >= 2 by luck alone (Harvey Liu Zhu 2016). And a
    bigger IC at a slower horizon does NOT mean "trade slower": IR ~ IC x
    sqrt(breadth) (Grinold Kahn), and a 1M signal makes ~12 independent bets
    a year versus ~1 at 4Q.

    Returns tidy rows [series, kind, horizon, months, mean_ic, t_stat, se,
    ir, n_periods] with kind in {composite, family, factor}. Horizons whose
    label column is absent (e.g. the synthetic panel only carries the model
    labels) are skipped.
    """
    series: list[tuple[str, str, str]] = []   # (display name, kind, column)
    for col, name in (("score_ew", "Composite (equal weight)"),
                      ("score_ml", "Composite (learned)")):
        if col in panel.columns and panel[col].notna().any():
            series.append((name, "composite", col))
    for c in sorted(panel.columns):
        if c.startswith("fam_") and c.endswith("__score"):
            label = c[len("fam_"):-len("__score")].replace("_", " ").title()
            series.append((label, "family", c))
    for f in config.active_factors():
        col = f"{f}__n"
        if col in panel.columns and panel[col].notna().any():
            series.append((f, "factor", col))

    rows = []
    for sfx, _days, months in config.TERM_STRUCTURE_HORIZONS:
        label_col = f"fwd_rel_ret_{sfx}"
        if label_col not in panel.columns or not panel[label_col].notna().any():
            continue
        lags = _nw_lags_months(months)
        for name, kind, col in series:
            ts = ic_series_for_label(panel, col, label_col)
            if ts.empty:
                continue
            mean, t, ir = _hac_tstat(ts["ic"], lags=lags)
            se = abs(mean / t) if (pd.notna(t) and t != 0) else np.nan
            rows.append({"series": name, "kind": kind, "horizon": sfx.upper(),
                         "months": months, "mean_ic": mean, "t_stat": t,
                         "se": se, "ir": ir, "n_periods": int(len(ts))})
    out = pd.DataFrame(rows, columns=["series", "kind", "horizon", "months",
                                      "mean_ic", "t_stat", "se", "ir", "n_periods"])
    if not out.empty:
        n_h = out["horizon"].nunique()
        logger.info("Horizon term structure: %d series x %d horizons measured",
                    out["series"].nunique(), n_h)
    return out


def factor_zoo_null(panel: pd.DataFrame, score_col: str, horizon_q: int,
                    n_draws: int = config.FACTOR_ZOO_DRAWS,
                    seed: int = config.FACTOR_ZOO_SEED) -> dict:
    """Multiple testing discipline (roadmap section 3; Harvey Liu Zhu 2016).

    With 20+ factors, SOME composite always looks good; the honest question
    is whether OUR model beats what random rummaging through the same zoo
    produces. Each draw builds an equal weight composite from a random subset
    (>= 3) of the direction aligned factor columns — sign consistent, so the
    null respects the documented red flag directions and is therefore HARDER
    to beat than white noise (the placebo covers that). Reports where the
    real model's mean IC sits in that null distribution; a p value near 0.5
    would mean the model is indistinguishable from factor mining.
    """
    rng = np.random.default_rng(seed)
    cols = [f"{f}__n" for f in config.active_factors() if f"{f}__n" in panel.columns]
    label = f"fwd_rel_ret_{horizon_q}q"
    if len(cols) < 4 or label not in panel.columns:
        return {"n_draws": 0, "real_ic": np.nan, "null_mean": np.nan,
                "null_p95": np.nan, "p_value": np.nan}
    real = summarize_ic(panel, score_col, horizon_q).mean_ic

    base = panel[["date", label]].copy()
    null_ics: list[float] = []
    for _ in range(n_draws):
        k = int(rng.integers(3, len(cols) + 1))
        pick = list(rng.choice(cols, size=k, replace=False))
        tmp = base.copy()
        tmp["_z"] = panel[pick].mean(axis=1, skipna=True)
        ics = []
        for _t, g in tmp.groupby("date"):
            d = g[["_z", label]].dropna()
            if len(d) < config.MIN_NAMES_PER_SECTOR * 2:
                continue
            rho, _ = spearmanr(d["_z"], d[label])
            if np.isfinite(rho):
                ics.append(-float(rho))
        if ics:
            null_ics.append(float(np.mean(ics)))
    arr = np.asarray(null_ics)
    if not len(arr) or pd.isna(real):
        return {"n_draws": int(len(arr)), "real_ic": real, "null_mean": np.nan,
                "null_p95": np.nan, "p_value": np.nan}
    out = {"n_draws": int(len(arr)), "real_ic": float(real),
           "null_mean": float(arr.mean()), "null_p95": float(np.quantile(arr, 0.95)),
           "p_value": float((arr >= real).mean())}
    logger.info("Factor zoo null: real IC %.4f vs null mean %.4f (p95 %.4f) over %d "
                "draws -> p=%.2f", out["real_ic"], out["null_mean"], out["null_p95"],
                out["n_draws"], out["p_value"])
    return out


def ic_by_vol_regime(panel: pd.DataFrame, score_col: str, horizon_q: int,
                     benchmark_px: pd.Series | None, window: int = 63) -> pd.DataFrame:
    """IC split by the benchmark's trailing realized volatility tercile.

    Regime conditioning, reporting only (roadmap section 3): the regime at
    each scoring date uses TRAILING benchmark volatility, so it is knowable
    at t; the tercile CUTS are full sample, which makes this a diagnostic
    table, not a tradeable rule — the UI says so. Answers "when is the sell
    signal trusted": a signal that only works in calm tape is a different
    product from one that holds up when volatility is elevated.
    """
    if benchmark_px is None or not len(benchmark_px):
        return pd.DataFrame(columns=["regime", "mean_ic", "t_stat", "n_periods",
                                     "avg_bench_vol"])
    ts = ic_time_series(panel, score_col, horizon_q)
    if ts.empty:
        return pd.DataFrame(columns=["regime", "mean_ic", "t_stat", "n_periods",
                                     "avg_bench_vol"])
    vol = benchmark_px.pct_change().rolling(window, min_periods=window).std() * np.sqrt(252)
    ts = ts.copy()
    ts["vol"] = vol.reindex(pd.to_datetime(ts["date"]), method="ffill").values
    ts = ts.dropna(subset=["vol"])
    if len(ts) < 12:
        return pd.DataFrame(columns=["regime", "mean_ic", "t_stat", "n_periods",
                                     "avg_bench_vol"])
    ts["regime"] = pd.qcut(ts["vol"], 3, labels=["calm", "normal", "stressed"])
    rows = []
    for reg in ["calm", "normal", "stressed"]:
        g = ts[ts["regime"] == reg]
        if g.empty:
            continue
        mean, t, _ = _hac_tstat(g["ic"], lags=_nw_lags(horizon_q))
        rows.append({"regime": reg, "mean_ic": mean, "t_stat": t,
                     "n_periods": int(len(g)), "avg_bench_vol": float(g["vol"].mean())})
    return pd.DataFrame(rows)


def screen_exposures(panel_q: pd.DataFrame, decile_col: str) -> pd.DataFrame:
    """Risk accounting lite (roadmap section 4): what does the sleeve tilt to?

    Per quarter end, the flagged sleeve's (worst decile) mean characteristic
    versus the whole selection universe, averaged across dates. A sell screen
    that mostly flags high beta names is a beta bet wearing a factor costume;
    this table says so out loud instead of leaving it to a risk model we do
    not yet have.
    """
    d = panel_q.dropna(subset=[decile_col])
    if d.empty:
        return pd.DataFrame(columns=["metric", "decile_10", "universe"])
    worst = d[d[decile_col] == config.N_DECILES]
    rows = []
    for col, label in [("beta_252d", "market beta (252d)"),
                       ("ivol_63d", "idiosyncratic vol (63d)"),
                       ("amihud_63d", "Amihud illiquidity (x1e9)"),
                       ("short_vol_ratio", "short volume share (3m)")]:
        if col not in d.columns or not d[col].notna().any():
            continue
        rows.append({"metric": label,
                     "decile_10": float(worst.groupby("date")[col].mean().mean()),
                     "universe": float(d.groupby("date")[col].mean().mean())})

    def _max_share(g: pd.DataFrame) -> float:
        c = g["gics_sector"].value_counts(normalize=True)
        return float(c.iloc[0]) if len(c) else np.nan

    rows.append({"metric": "largest sector share",
                 "decile_10": float(worst.groupby("date").apply(_max_share).mean()),
                 "universe": float(d.groupby("date").apply(_max_share).mean())})
    return pd.DataFrame(rows)


# =============================================================================
# Paired IC test — the promotion gate for the learned model
# =============================================================================
def paired_ic_test(panel: pd.DataFrame, col_a: str, col_b: str, horizon_q: int) -> dict:
    """HAC t stat on the per date IC DIFFERENCE (col_a − col_b), same dates only.

    A point estimate edge (IC_a > IC_b) can be pure noise; pairing by date
    removes the common cross sectional component and tests whether the edge is
    systematic. Promotion requires mean_diff > 0 and t ≥ config.PROMOTION_MIN_T.
    """
    a = ic_time_series(panel, col_a, horizon_q).set_index("date")["ic"]
    b = ic_time_series(panel, col_b, horizon_q).set_index("date")["ic"]
    common = a.index.intersection(b.index)
    if len(common) < 3:
        return {"mean_diff": np.nan, "t_stat": np.nan, "n_periods": int(len(common)),
                "promote": False}
    diff = (a.loc[common] - b.loc[common])
    mean, t, _ = _hac_tstat(diff, lags=_nw_lags(horizon_q))
    promote = bool(pd.notna(mean) and pd.notna(t) and mean > 0 and t >= config.PROMOTION_MIN_T)
    logger.info("Paired IC test %s vs %s: mean diff=%+.4f t=%+.2f over %d dates -> %s",
                col_a, col_b, mean, t, len(common),
                "PROMOTE" if promote else "keep baseline")
    return {"mean_diff": mean, "t_stat": t, "n_periods": int(len(common)), "promote": promote}


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
    """Side by side OOS IC for equal weight vs IC weighted blend vs learned."""
    rows = []
    for col, name in [("score_ew", "equal_weight"), ("score_icw", "ic_weighted"),
                      ("score_ml", "learned_weight")]:
        if col not in panel.columns or not panel[col].notna().any():
            continue
        s = summarize_ic(panel, col, horizon_q)
        rows.append({"model": name, "score_col": col, "mean_ic": s.mean_ic,
                     "t_stat": s.t_stat, "ir": s.ir, "hit_rate": s.hit_rate,
                     "n_periods": s.n_periods})
    return pd.DataFrame(rows)
