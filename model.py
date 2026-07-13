"""Scoring models: the equal weight baseline and an optional learned weight model.

BASELINE (always shipped, always the default unless explicitly beaten):
    score_ew = mean over available direction aligned sector neutral factors.
This is the Piper style equal weight composite. Because every factor was already
sign flipped to point the same way, the mean needs no further weighting — and
that internal consistency is the whole point (no equal weight vs fitted mismatch).

LEARNED WEIGHT (optional, walk forward, OOS only):
    At each rebalance date t, fit a cross sectional model on the POOLED panel of
    dates strictly < t (features = the ``__n`` columns, label = forward relative
    return), then predict the cross section at t. Never an in sample fit; never a
    global fit. ``validate.py`` compares its OOS IC to the baseline and decides
    whether it earns the default — see the README. We never present fitted then-
    ignored weights.

Both models then assign a **sector neutral decile** at each date (1 = best /
most expected outperformance, ``N_DECILES`` = worst / strongest sell candidate).
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge, LogisticRegression
from sklearn.ensemble import GradientBoostingRegressor

import config

logger = logging.getLogger(__name__)


def neutral_columns(panel: pd.DataFrame) -> list[str]:
    return [c for c in panel.columns if c.endswith("__n")]


def _group_keys(panel: pd.DataFrame) -> list[str]:
    keys = ["date", "gics_sector"]
    if "index_name" in panel.columns:
        keys.append("index_name")
    return keys


# =============================================================================
# Sector neutral decile
# =============================================================================
def assign_sector_deciles(panel: pd.DataFrame, score_col: str, n: int = config.N_DECILES) -> pd.Series:
    """Within each peer group (date, sector[, index]), bucket ``score_col``
    into ``n`` deciles.

    Decile 1 = lowest score (best expected relative return), decile n = highest
    score (worst — the sell sleeve). Robust to ties / small groups via rank.
    """
    def _decile(s: pd.Series) -> pd.Series:
        valid = s.dropna()
        if len(valid) < n:
            # too few to form n buckets: scale rank into [1, n]
            r = s.rank(method="first")
            return np.ceil(r / len(valid) * n).clip(1, n) if len(valid) else r
        r = s.rank(method="first", pct=True)
        return np.ceil(r * n).clip(1, n)

    return panel.groupby(_group_keys(panel), group_keys=False)[score_col].apply(_decile)


# =============================================================================
# Family balanced baseline (the "equal weight by information" composite)
# =============================================================================
def equal_weight_score(panel: pd.DataFrame) -> pd.DataFrame:
    """Add ``score_ew`` + ``decile_ew`` via the FAMILY BALANCED composite.

    Three deliberate steps replace the old flat mean over all factors:

    1. **Family means first.** Factors are averaged within their family
       (config.FACTOR_GROUPS), then the family scores are averaged. Four
       collinear valuation ratios therefore cast ONE family vote — and the
       price derived families (Momentum, Volatility) can never swamp the
       fundamentals no matter how many price factors are added.
    2. **Coverage floor.** A name needs >= MIN_FACTORS_FOR_SCORE populated
       factors across >= MIN_FAMILIES_FOR_SCORE families, else it is not
       scored (never guessed).
    3. **Re-standardization.** The composite is z scored again within each
       peer group, because the mean of 2 family scores has a different
       variance than the mean of 6 — without this, thin coverage names land
       in extreme deciles as a pure data artifact.
    """
    cols = neutral_columns(panel)
    if not cols:
        raise ValueError("No neutralized factor columns found; run neutralize_factors first")
    df = panel.copy()

    fam_of = {f"{f}__n": g for f, g in config.FACTOR_GROUPS.items() if f"{f}__n" in cols}
    families = sorted(set(fam_of.values()))
    fam_cols: dict[str, list[str]] = {g: [c for c, gg in fam_of.items() if gg == g] for g in families}

    fam_scores = pd.DataFrame(index=df.index)
    for g, gcols in fam_cols.items():
        fam_scores[g] = df[gcols].mean(axis=1, skipna=True)

    df["n_factors_used"] = df[list(fam_of)].notna().sum(axis=1)
    df["n_families_used"] = fam_scores.notna().sum(axis=1)
    raw_score = fam_scores.mean(axis=1, skipna=True)
    thin = ((df["n_factors_used"] < config.MIN_FACTORS_FOR_SCORE)
            | (df["n_families_used"] < config.MIN_FAMILIES_FOR_SCORE))
    raw_score[thin] = np.nan
    df["score_ew_raw"] = raw_score

    # Re-standardize within peer group so coverage regimes are comparable.
    def _restd(s: pd.Series) -> pd.Series:
        mu, sd = s.mean(), s.std(ddof=0)
        return (s - mu) / sd if (sd and np.isfinite(sd) and sd > 0) else s * 0.0

    df["score_ew"] = (df.groupby(_group_keys(df), group_keys=False)["score_ew_raw"]
                        .apply(_restd))
    df["decile_ew"] = assign_sector_deciles(df, "score_ew")
    logger.info("Family balanced score: %d/%d rows scored (>=%d factors over >=%d families; "
                "%d families active)",
                int(df["score_ew"].notna().sum()), len(df),
                config.MIN_FACTORS_FOR_SCORE, config.MIN_FAMILIES_FOR_SCORE, len(families))
    return df


# =============================================================================
# Learned weight model (walk forward)
# =============================================================================
def _fit_predict(model_name: str, X_tr: np.ndarray, y_tr: np.ndarray, X_te: np.ndarray) -> np.ndarray:
    if model_name == "ridge":
        m = Ridge(alpha=config.RIDGE_ALPHA)
        m.fit(X_tr, y_tr)
        return m.predict(X_te)
    if model_name == "gbm":
        m = GradientBoostingRegressor(n_estimators=200, max_depth=3, subsample=0.8,
                                      learning_rate=0.03)
        m.fit(X_tr, y_tr)
        return m.predict(X_te)
    if model_name == "logistic":
        # Classify "bottom quartile relative return" then use P(bad) as the score.
        thresh = np.quantile(y_tr, 0.25)
        cls = (y_tr <= thresh).astype(int)
        if cls.sum() == 0 or cls.sum() == len(cls):
            return np.full(X_te.shape[0], np.nan)
        m = LogisticRegression(C=1.0, max_iter=500)
        m.fit(X_tr, cls)
        return m.predict_proba(X_te)[:, 1]
    raise ValueError(f"Unknown LEARNED_MODEL {model_name!r}")


def learned_weight_score(
    panel: pd.DataFrame,
    horizon_q: int = config.DEFAULT_HORIZON_Q,
    model_name: str = config.LEARNED_MODEL,
    min_train_periods: int = config.WALK_FORWARD_MIN_TRAIN_PERIODS,
) -> pd.DataFrame:
    """Walk forward OOS score ``score_ml`` + ``decile_ml``.

    Features = neutral factor columns (NaN imputed to 0 = sector neutral mean,
    since they are already sector z scores). Label = forward relative return at
    ``horizon_q``. Trains only on dates strictly before each prediction date.
    """
    label = f"fwd_rel_ret_{horizon_q}q"
    cols = neutral_columns(panel)
    df = panel.copy()
    df["score_ml"] = np.nan

    dates = sorted(df["date"].unique())
    pos = {d: df.index[df["date"] == d] for d in dates}
    # Train on the SELECTION universe only (IMA picks from the S&P 600); the
    # fitted model still scores every row so graduates stay monitorable.
    in_selection = (df["index_name"] == config.SELECTION_INDEX
                    if "index_name" in df.columns else pd.Series(True, index=df.index))

    n_fit = 0
    for i, t in enumerate(dates):
        if i < min_train_periods:
            continue
        train_mask = (df["date"] < t) & in_selection
        tr = df[train_mask & df[label].notna()]
        if len(tr) < 50:
            continue
        X_tr = tr[cols].fillna(0.0).values
        y_tr = tr[label].values
        te_idx = pos[t]
        X_te = df.loc[te_idx, cols].fillna(0.0).values
        try:
            pred = _fit_predict(model_name, X_tr, y_tr, X_te)
        except Exception as exc:  # noqa: BLE001
            logger.debug("learned fit failed at %s: %s", t, exc)
            continue
        # Higher score must mean MORE underperformance (sell). The label is a
        # return, so a model predicting low returns = high sell risk: negate.
        df.loc[te_idx, "score_ml"] = -pred
        n_fit += 1

    df["decile_ml"] = assign_sector_deciles(df, "score_ml")
    logger.info("Learned weight (%s, h=%dq): %d OOS cross sections scored",
                model_name, horizon_q, n_fit)
    return df


def default_score_column(panel: pd.DataFrame) -> str:
    """Which score the app treats as primary. Baseline unless learned is enabled
    AND present. validate.py is what justifies flipping config.USE_LEARNED_WEIGHTS."""
    if config.USE_LEARNED_WEIGHTS and "score_ml" in panel.columns and panel["score_ml"].notna().any():
        return "score_ml"
    return "score_ew"
