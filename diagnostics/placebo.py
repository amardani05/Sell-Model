"""Placebo test: shuffling the score WITHIN each cross section must kill the IC.

If a model's IC survives randomly permuting the scores inside each date, the IC
was an artifact (leakage, a bug, or accidental alignment), not skill. A healthy
model shows a clearly positive real IC and a placebo IC indistinguishable from 0.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

import config
from validate import summarize_ic

logger = logging.getLogger(__name__)

PLACEBO_TOL = 0.03   # |placebo mean IC| must be below this


def shuffle_scores_within_date(panel: pd.DataFrame, score_col: str, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    df = panel.copy()
    def _shuf(s: pd.Series) -> pd.Series:
        vals = s.values.copy()
        rng.shuffle(vals)
        return pd.Series(vals, index=s.index)
    df[score_col] = df.groupby("date", group_keys=False)[score_col].apply(_shuf)
    return df


def run_placebo(panel: pd.DataFrame, score_col: str = "score_ew",
                horizon_q=config.DEFAULT_HORIZON, n_trials: int = 10) -> dict:
    real = summarize_ic(panel, score_col, horizon_q)
    placebo_means = []
    for k in range(n_trials):
        sh = shuffle_scores_within_date(panel, score_col, seed=k)
        placebo_means.append(summarize_ic(sh, score_col, horizon_q).mean_ic)
    placebo_mean = float(np.nanmean(placebo_means))
    passed = abs(placebo_mean) < PLACEBO_TOL and (real.mean_ic > placebo_mean)
    result = {
        "real_ic": real.mean_ic, "real_t": real.t_stat,
        "placebo_ic_mean": placebo_mean,
        "placebo_ic_std": float(np.nanstd(placebo_means)),
        "tolerance": PLACEBO_TOL, "passed": bool(passed),
    }
    logger.info("PLACEBO: real IC=%.4f vs placebo IC=%.4f (tol %.2f) -> %s",
                real.mean_ic, placebo_mean, PLACEBO_TOL, "PASS" if passed else "FAIL")
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    from diagnostics.synth import make_synthetic_panel
    from feature_engine import neutralize_factors
    from model import equal_weight_score
    panel = make_synthetic_panel()
    panel = equal_weight_score(neutralize_factors(panel))
    res = run_placebo(panel)
    assert res["passed"], f"Placebo failed: {res}"
    print("Placebo PASS", res)
