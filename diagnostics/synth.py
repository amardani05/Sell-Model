"""Synthetic panel with a PLANTED cross sectional signal.

Used by the diagnostics (so they run deterministically with no network) and by
``main.py --synthetic`` to demonstrate the validation/backtest machinery when
yfinance's shallow fundamental history can't support a deep backtest on its own.

The generator plants a known relationship — forward sector relative return is a
negative function of a handful of the (direction aligned) factors plus noise —
so a correct pipeline must show POSITIVE IC, a POSITIVE decile spread, and
monotone deciles. Shuffling the score (placebo) must erase all of it.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import config

SECTORS = ["Industrials", "Information Technology", "Health Care",
           "Consumer Discretionary", "Financials", "Materials"]
# Factors that actually drive returns in the synthetic world (the rest are noise).
PREDICTIVE = ["mom_12_1", "pe_ratio", "asset_growth_yoy", "accruals_ocf_ni"]


def make_synthetic_panel(
    n_dates: int = 24, names_per_sector: int = 40,
    signal: float = 0.04, noise: float = 0.06, seed: int = 7,
    delist_frac: float = 0.02,
) -> pd.DataFrame:
    """Return a RAW panel (pre neutralize) shaped exactly like the real one."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2018 03 31", periods=n_dates, freq="QE")
    factors = config.BASE_FACTORS

    tickers, sectors = [], []
    for s_i, sec in enumerate(SECTORS):
        for j in range(names_per_sector):
            tickers.append(f"S{s_i}N{j:02d}")
            sectors.append(sec)
    sector_of = dict(zip(tickers, sectors))

    rows = []
    for t in dates:
        # sector level common forward return (so RELATIVE return removes it)
        sector_ret = {sec: rng.normal(0.0, 0.05) for sec in SECTORS}
        # raw factor draws
        raw = {f: dict(zip(tickers, rng.normal(0, 1, len(tickers)))) for f in factors}
        for tk in tickers:
            sec = sector_of[tk]
            # direction aligned latent exposure from predictive factors
            expo = 0.0
            for f in PREDICTIVE:
                expo += config.RED_FLAG_DIRECTION.get(f, 1) * raw[f][tk]
            expo /= len(PREDICTIVE)
            rel = -signal * expo + rng.normal(0, noise)   # higher red flag => worse
            abs_ret = sector_ret[sec] + rel
            rec = {"date": pd.Timestamp(t), "ticker": tk, "gics_sector": sec}
            for f in factors:
                rec[f] = raw[f][tk]
            rec["short_pct_float"] = abs(rng.normal(0.05, 0.04))
            rec["fwd_ret_1q"] = abs_ret
            rec["fwd_ret_2q"] = abs_ret + sector_ret[sec] + rng.normal(0, noise)
            rec["delisted"] = False
            rows.append(rec)

    panel = pd.DataFrame(rows)

    # plant a few delistings: terminal return, strongest underperformer
    dl = panel.sample(frac=delist_frac, random_state=seed).index
    panel.loc[dl, "fwd_ret_1q"] = config.DELISTING_TERMINAL_RETURN
    panel.loc[dl, "fwd_ret_2q"] = config.DELISTING_TERMINAL_RETURN
    panel.loc[dl, "delisted"] = True

    # sector relative labels
    for h in config.HORIZONS_Q:
        col = f"fwd_ret_{h}q"
        med = panel.groupby(["date", "gics_sector"])[col].transform("median")
        panel[f"fwd_rel_ret_{h}q"] = panel[col] - med
    return panel
