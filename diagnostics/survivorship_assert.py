"""Survivorship assertion: delisted names must be CARRIED, not dropped.

Two checks:
  1. Constructive — build a tiny price matrix where one name trades for a year
     and then goes dark (delists). Run the real delisting aware forward return
     function and assert the delisted name receives ``DELISTING_TERMINAL_RETURN``
     over the horizon that spans its disappearance, while a survivor gets a
     normal return. A survivorship biased implementation would return NaN/drop it.
  2. Membership honesty — warn if the universe is running on a current only
     (today seeded) membership snapshot rather than a true point in time store.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

import config
from feature_engine import _forward_returns, _quarter_end_dates
from universe import has_real_membership

logger = logging.getLogger(__name__)


def assert_delisting_carried() -> dict:
    """Synthetic delisting must surface as a terminal return, not a dropped row."""
    # ~2 years of business days; SURV trades the whole time, DEAD stops at ~1y.
    idx = pd.bdate_range("2021 01 01", periods=2 * config.TRADING_DAYS_PER_QUARTER * 4)
    surv = pd.Series(100.0 * (1.005) ** np.arange(len(idx)), index=idx)
    dead = surv.copy()
    cutoff = config.TRADING_DAYS_PER_QUARTER * 4  # dies after ~1 year
    dead.iloc[cutoff:] = np.nan
    prices = pd.DataFrame({"SURV": surv, "DEAD": dead})

    q_dates = _quarter_end_dates(prices)
    fwd = _forward_returns(prices, q_dates, horizon_q=config.DEFAULT_HORIZON_Q)

    # Find a rebalance date that sits one horizon BEFORE the death date.
    death_date = idx[cutoff - 1]
    horizon_days = config.DEFAULT_HORIZON_Q * config.TRADING_DAYS_PER_QUARTER
    span_dates = [t for t in q_dates if t < death_date <= idx[min(len(idx) - 1, idx.searchsorted(t) + horizon_days)]]

    carried = False
    for t in span_dates:
        v = fwd.at[t, "DEAD"]
        if pd.notna(v) and abs(v - config.DELISTING_TERMINAL_RETURN) < 1e-9:
            carried = True
            break
    survivor_ok = fwd["SURV"].notna().any()
    passed = carried and survivor_ok
    logger.info("SURVIVORSHIP: delisted carried to terminal=%s, survivor scored=%s -> %s",
                carried, survivor_ok, "PASS" if passed else "FAIL")
    return {"delisted_carried": carried, "survivor_scored": bool(survivor_ok),
            "terminal_return": config.DELISTING_TERMINAL_RETURN, "passed": bool(passed)}


def assert_membership_is_point_in_time() -> dict:
    real = has_real_membership()
    if not real:
        logger.warning("SURVIVORSHIP: membership store is CURRENT ONLY (survivorship biased). "
                       "Backtest history is optimistic until a true PIT store is supplied.")
    return {"real_point_in_time": bool(real),
            "passed": True,  # not a hard failure; the warning is the deliverable
            "note": "current only membership is survivorship biased" if not real else "PIT store present"}


def run_survivorship() -> dict:
    out = {
        "delisting_carried": assert_delisting_carried(),
        "membership": assert_membership_is_point_in_time(),
    }
    out["passed"] = out["delisting_carried"]["passed"]
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    res = run_survivorship()
    assert res["passed"], res
    print("Survivorship PASS", res)
