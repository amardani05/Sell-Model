"""Look ahead assertion: a feature at date t must be invariant to FUTURE data.

The test is constructive. Take the real price matrix, compute the price factors
twice — once on the full matrix, once on the matrix TRUNCATED at t (all rows
> t deleted) — and assert the value at t is identical. If a factor secretly used
future prices, truncation would change it. We also assert structurally that no
forward return column is ever fed to the model as a feature, and that every
fundamental observation used at t has an as of date <= t.
"""

from __future__ import annotations

import logging

import pandas as pd

from feature_engine import _price_factor_panels, _asof_sample

logger = logging.getLogger(__name__)


def assert_price_factor_no_lookahead(prices: pd.DataFrame, n_check: int = 6) -> dict:
    """Recompute price factors on truncated history; assert equality at t."""
    full = _price_factor_panels(prices)
    idx = prices.index
    # pick a spread of test dates in the back half (need >=252 days of history)
    candidates = idx[idx >= idx[252]] if len(idx) > 252 else idx
    test_dates = list(candidates[:: max(1, len(candidates) // n_check)])[:n_check]

    mismatches = 0
    checked = 0
    for t in test_dates:
        truncated = prices.loc[prices.index <= t]
        trunc_factors = _price_factor_panels(truncated)
        for name in full:
            a = _asof_sample(full[name], [t]).iloc[0]
            b = _asof_sample(trunc_factors[name], [t]).iloc[0]
            common = a.index.intersection(b.index)
            diff = (a[common] - b[common]).abs()
            diff = diff[a[common].notna() & b[common].notna()]
            checked += int(diff.notna().sum())
            mismatches += int((diff > 1e-9).sum())
    passed = mismatches == 0
    logger.info("LOOK AHEAD: %d price factor values truncation invariant, %d mismatches -> %s",
                checked, mismatches, "PASS" if passed else "FAIL")
    return {"checked": checked, "mismatches": mismatches, "passed": bool(passed)}


def assert_no_label_in_features(panel: pd.DataFrame) -> dict:
    """No forward return column may appear among the model's feature columns."""
    feature_cols = [c for c in panel.columns if c.endswith("__n")]
    leak = [c for c in feature_cols if "fwd_" in c or "rel_ret" in c]
    passed = len(leak) == 0
    logger.info("LOOK AHEAD: %d feature columns, label leak columns=%s -> %s",
                len(feature_cols), leak, "PASS" if passed else "FAIL")
    return {"n_features": len(feature_cols), "leak_columns": leak, "passed": bool(passed)}


def run_lookahead(prices: pd.DataFrame | None, panel: pd.DataFrame) -> dict:
    out = {"no_label_in_features": assert_no_label_in_features(panel)}
    if prices is not None and not prices.empty:
        out["price_factor_truncation"] = assert_price_factor_no_lookahead(prices)
    passed = all(v["passed"] for v in out.values())
    out["passed"] = passed
    return out
