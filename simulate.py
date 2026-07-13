"""Monte Carlo simulation of IMA style concentrated portfolios.

IMA holds ~20 names picked from the S&P 600 (kept if they graduate to the 400).
For a book that concentrated, a single simulated path is dominated by luck —
one +80% quarter in one holding decides the whole track record. So instead of
one path, this draws MANY random 20 name portfolios from the scored universe
under each screening rule and compares the resulting DISTRIBUTIONS:

    full        pick from every scored name (the unscreened picker)
    ex10        pick from everything except the worst sell decile
    ex9_10      pick from everything except deciles 9-10
    top_half    pick only from deciles 1-5

If the sell screen has value for a concentrated long only picker, the screened
distributions should shift right (higher median CAGR) and/or lose their left
tail (fewer disaster portfolios). If the distributions are indistinguishable,
the screen is not yet paying for its constraint — also worth knowing.

Mechanics: at every rebalance date each trial draws ``n_names`` names uniformly
without replacement from the tier's eligible pool and equal weights them for
one quarter (using the panel's delisting aware, splice gated ``fwd_ret_1q``).
Dates where any tier cannot field a full portfolio are dropped from ALL tiers
so every tier is measured on identical quarters. No transaction costs are
charged: every tier redraws identically, so costs would shift all tiers
equally and cancel in the comparison.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

import config

logger = logging.getLogger(__name__)

TIERS: list[tuple[str, str]] = [
    ("full", "Full universe (no screen)"),
    ("ex10", "Exclude worst decile (10)"),
    ("ex9_10", "Exclude deciles 9 and 10"),
    ("top_half", "Top half only (deciles 1 to 5)"),
]


def _eligible(g: pd.DataFrame, tier: str, decile_col: str) -> np.ndarray:
    d = g[decile_col]
    if tier == "full":
        mask = d.notna()
    elif tier == "ex10":
        mask = d < config.N_DECILES
    elif tier == "ex9_10":
        mask = d < config.N_DECILES - 1
    elif tier == "top_half":
        mask = d <= config.N_DECILES // 2
    else:
        raise ValueError(f"unknown tier {tier!r}")
    return g.loc[mask, "fwd_ret_1q"].values.astype(float)


def simulate_ima_portfolios(
    panel: pd.DataFrame,
    decile_col: str,
    n_names: int = config.MC_PORTFOLIO_SIZE,
    n_trials: int = config.MC_N_TRIALS,
    seed: int = config.MC_SEED,
) -> dict:
    """Distribution of CAGRs for random ``n_names`` portfolios per screening tier."""
    rng = np.random.default_rng(seed)
    d = panel.dropna(subset=["fwd_ret_1q", decile_col])[["date", decile_col, "fwd_ret_1q"]]

    # Build per date pools per tier; keep only dates every tier can fully field.
    pools: dict[pd.Timestamp, dict[str, np.ndarray]] = {}
    for t, g in d.groupby("date"):
        by_tier = {tier: _eligible(g, tier, decile_col) for tier, _ in TIERS}
        if all(len(v) >= n_names for v in by_tier.values()):
            pools[pd.Timestamp(t)] = by_tier
    dates = sorted(pools)
    if len(dates) < 4:
        logger.warning("MC simulation: only %d usable dates; skipping", len(dates))
        return {}

    ann = 4
    years = len(dates) / ann
    out: dict = {"dates": [dt.isoformat() for dt in dates],
                 "n_names": int(n_names), "n_trials": int(n_trials),
                 "tiers": {}}
    full_median = None
    for tier, label in TIERS:
        # returns matrix [n_trials x n_dates]
        rets = np.empty((n_trials, len(dates)))
        for j, dt in enumerate(dates):
            pool = pools[dt][tier]
            for i in range(n_trials):
                pick = rng.choice(len(pool), size=n_names, replace=False)
                rets[i, j] = pool[pick].mean()
        equity = np.cumprod(1.0 + rets, axis=1)
        cagrs = equity[:, -1] ** (1.0 / years) - 1.0
        pct = {f"p{p}": float(np.percentile(cagrs, p)) for p in (5, 25, 50, 75, 95)}
        if tier == "full":
            full_median = pct["p50"]
        bands = {f"p{p}": np.percentile(equity, p, axis=0).round(4).tolist()
                 for p in (5, 25, 50, 75, 95)}
        out["tiers"][tier] = {
            "label": label,
            "cagr": {**pct, "mean": float(cagrs.mean())},
            "prob_beat_full_median": (float((cagrs > full_median).mean())
                                      if full_median is not None else None),
            "trial_cagrs": np.round(cagrs, 4).tolist(),
            "equity_bands": bands,
        }
        logger.info("MC %-10s median CAGR=%+.1f%%  p5=%+.1f%%  p95=%+.1f%%",
                    tier, pct["p50"] * 100, pct["p5"] * 100, pct["p95"] * 100)
    return out
