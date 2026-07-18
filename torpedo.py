"""Torpedo screener: the absolute, whole universe risk view.

This is the deliberate counterpart to the sell model and answers a different
question. Where the sell model ranks a name against its GICS sector peers and
targets relative underperformance, the torpedo screener ranks a name against the
WHOLE universe and targets absolute blow up / drawdown risk. It is integrated
here as a contrast lens, not as the primary output.

Mechanics (see config.TORPEDO_FEATURES / TORPEDO_RISK_DIRECTION):
  1. winsorize each risk feature at each date;
  2. z score it across the WHOLE universe on that date (NOT within sector);
  3. flip signs so higher always means more risk;
  4. average the available features into a composite (torpedo_score);
  5. convert the composite to a 0 to 100 universe percentile (torpedo_pct)
     and a coarse tier (Stable / Mainstream / Elevated).

The output columns are added to the panel so the webapp can plot the sell model
decile against the torpedo percentile on the same names.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

import config

logger = logging.getLogger(__name__)


def _winsorize(s: pd.Series, pct: float) -> pd.Series:
    if s.notna().sum() < 3 or pct <= 0:
        return s
    return s.clip(s.quantile(pct), s.quantile(1 - pct))


def _tier(pct: float) -> str:
    if pct is None or not np.isfinite(pct):
        return "Unknown"
    for lo, hi, name in config.TORPEDO_TIERS:
        if lo <= pct < hi:
            return name
    return config.TORPEDO_TIERS[-1][2]


def compute_torpedo(panel: pd.DataFrame) -> pd.DataFrame:
    """Add torpedo_score, torpedo_pct, torpedo_tier to the panel.

    Every torpedo feature is z scored across the whole universe at each date
    (the defining difference from the sector neutral sell model), aligned so
    higher means more absolute risk, then averaged into a composite that is
    turned into a universe percentile and tier.
    """
    df = panel.copy()
    features = [f for f in config.TORPEDO_FEATURES if f in df.columns]
    if not features:
        logger.warning("No torpedo features present in panel; skipping")
        df["torpedo_score"] = np.nan
        df["torpedo_pct"] = np.nan
        df["torpedo_tier"] = "Unknown"
        return df

    def _neutral_whole_universe(group: pd.Series) -> pd.Series:
        g = _winsorize(group.astype(float), config.WINSORIZE_PCT)
        mu, sd = g.mean(), g.std(ddof=0)
        return (g - mu) / sd if (sd and np.isfinite(sd) and sd > 0) else g * 0.0

    # z score each feature across the WHOLE universe at each date (by date only,
    # never by sector) and align to the risk direction.
    gb = df.groupby("date", group_keys=False)
    z_cols = []
    for f in features:
        direction = config.TORPEDO_RISK_DIRECTION.get(f, 1)
        col = f"{f}__t"
        df[col] = gb[f].apply(_neutral_whole_universe) * direction
        z_cols.append(col)

    df["n_torpedo_used"] = df[z_cols].notna().sum(axis=1)
    df["torpedo_score"] = df[z_cols].mean(axis=1, skipna=True)
    df.loc[df["n_torpedo_used"] == 0, "torpedo_score"] = np.nan

    # 0 to 100 universe percentile of the composite, per date.
    df["torpedo_pct"] = (
        df.groupby("date", group_keys=False)["torpedo_score"]
          .apply(lambda s: s.rank(pct=True) * 100.0)
    )
    df["torpedo_tier"] = df["torpedo_pct"].map(_tier)

    scored = int((df["n_torpedo_used"] > 0).sum())
    logger.info("Torpedo score: %d/%d rows scored across %d features (whole universe z score)",
                scored, len(df), len(features))
    return df


def latest_torpedo_table(panel: pd.DataFrame) -> pd.DataFrame:
    """Latest cross section ranked by absolute torpedo risk, high to low."""
    if "torpedo_pct" not in panel.columns:
        return pd.DataFrame()
    latest_date = panel["date"].max()
    latest = panel[panel["date"] == latest_date].copy()
    latest = latest.dropna(subset=["torpedo_pct"])
    return latest.sort_values("torpedo_pct", ascending=False)


def torpedo_reliability(panel: pd.DataFrame, horizon) -> pd.DataFrame:
    """Does a high torpedo percentile actually precede absolute damage?

    The honest test for an ABSOLUTE risk lens is absolute outcomes, not
    sector relative ranks: per torpedo decile (whole universe, both indexes,
    exactly as the screener ranks), the frequency of a genuine torpedo hit
    over the forward horizon window. A hit is an absolute total return at or
    below -20% (damage) or -50% (blow up). Delistings are included at the
    terminal return, so bankruptcies count as hits instead of vanishing.
    Frequencies are computed per date and then averaged across dates (Fama
    MacBeth style) so one crash quarter cannot dominate the curve.
    """
    import config as _config
    sfx, _months = _config.horizon_spec(horizon)
    label = f"fwd_ret_{sfx}"
    if "torpedo_pct" not in panel.columns or label not in panel.columns:
        return pd.DataFrame(columns=["torpedo_decile", "p_loss20", "p_loss50",
                                     "mean_abs_ret", "median_abs_ret",
                                     "n_obs", "n_dates"])
    d = panel.dropna(subset=["torpedo_pct", label])[["date", "torpedo_pct", label]].copy()
    if d.empty:
        return pd.DataFrame(columns=["torpedo_decile", "p_loss20", "p_loss50",
                                     "mean_abs_ret", "median_abs_ret",
                                     "n_obs", "n_dates"])
    d["torpedo_decile"] = np.ceil(d["torpedo_pct"] / 10.0).clip(1, 10).astype(int)
    per_date = d.groupby(["date", "torpedo_decile"]).agg(
        p20=(label, lambda s: float((s <= -0.20).mean())),
        p50=(label, lambda s: float((s <= -0.50).mean())),
        mean_ret=(label, "mean"),
        med_ret=(label, "median"),
        n=(label, "size"),
    ).reset_index()
    agg = per_date.groupby("torpedo_decile").agg(
        p_loss20=("p20", "mean"),
        p_loss50=("p50", "mean"),
        mean_abs_ret=("mean_ret", "mean"),
        median_abs_ret=("med_ret", "mean"),
        n_obs=("n", "sum"),
        n_dates=("n", "size"),
    ).reset_index()
    logger.info("Torpedo reliability (h=%s): decile 10 P(<=-20%%)=%.1f%% vs decile 1 %.1f%%",
                sfx, float(agg.iloc[-1]["p_loss20"]) * 100, float(agg.iloc[0]["p_loss20"]) * 100)
    return agg
