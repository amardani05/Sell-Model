"""Analyst override layer — annotations that NEVER touch the score.

Design: docs/override-layer-design.md. The quantitative score is immutable; an
override is a structured, attributed, expiring disagreement filed next to it:

    date, ticker, analyst, direction, reason_code, factor, note, expires

and the whole payoff is that overrides are SCORED every quarter: once an override's
window has realized relative returns, we check whether the name behaved the way
the analyst said (direction) or the way the model implied (the opposite — an
override exists precisely because the analyst disagrees). Hit rates are
published overall and per reason code. `thesis_disagreement` is tracked
separately because the clinical-vs-actuarial literature (Meehl 1954; Grove &
Meehl 2000) predicts that bucket underperforms — the scoreboard finds out.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

import config

logger = logging.getLogger(__name__)

REASON_CODES: list[str] = [
    "corporate_action",         # pending M&A, spin, tender, special dividend
    "accounting_artifact",      # input is real but economically misleading
    "data_error",               # the underlying data is wrong
    "new_information",          # post-statement contract, guidance, litigation
    "structural_peer_mismatch", # the sector peer group is unfair to the name
    "thesis_disagreement",      # plain disagreement — allowed, tracked apart
]
DIRECTIONS = ("less_risky", "more_risky")

COLUMNS = ["date", "ticker", "analyst", "direction", "reason_code",
           "factor", "note", "expires"]


def load_overrides(path=config.OVERRIDES_CSV) -> pd.DataFrame:
    """Read and validate the override log. Bad rows are dropped LOUDLY."""
    if not path.exists():
        return pd.DataFrame(columns=COLUMNS)
    df = pd.read_csv(path, comment="#", skip_blank_lines=True,
                     dtype=str, keep_default_na=False)
    if df.empty:
        return pd.DataFrame(columns=COLUMNS)
    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        logger.warning("overrides.csv missing columns %s — ignoring file", missing)
        return pd.DataFrame(columns=COLUMNS)

    df = df[COLUMNS].copy()
    df["ticker"] = df["ticker"].str.upper().str.strip()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["expires"] = pd.to_datetime(df["expires"], errors="coerce")
    # default expiry: OVERRIDE_MAX_AGE_QUARTERS after filing
    no_exp = df["expires"].isna() & df["date"].notna()
    df.loc[no_exp, "expires"] = df.loc[no_exp, "date"] + pd.DateOffset(
        months=3 * config.OVERRIDE_MAX_AGE_QUARTERS)

    bad = (df["date"].isna() | ~df["direction"].isin(DIRECTIONS)
           | ~df["reason_code"].isin(REASON_CODES) | (df["ticker"] == "")
           | (df["analyst"].str.strip() == ""))
    if bad.any():
        for _, r in df[bad].iterrows():
            logger.warning("override REJECTED (invalid field): %s", r.to_dict())
        df = df[~bad]
    logger.info("Overrides: %d valid rows loaded from %s", len(df), path)
    return df.reset_index(drop=True)


def active_overrides(overrides: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame:
    """Overrides in force at ``as_of`` (filed on or before, not yet expired)."""
    if overrides.empty:
        return overrides
    as_of = pd.Timestamp(as_of)
    m = (overrides["date"] <= as_of) & (overrides["expires"] >= as_of)
    return overrides[m].reset_index(drop=True)


def score_overrides(overrides: pd.DataFrame, panel: pd.DataFrame) -> dict:
    """Quarterly scoreboard: did overridden names side with the analyst?

    For each override and each panel cross section t in [filed, expires] with a
    realized ``fwd_rel_ret_1q`` for that ticker:
        analyst_correct := (rel_ret < 0) == (direction == "more_risky")
    The model's implied call is the opposite of the override (an override IS a
    disagreement), so model hit rate = 1 − analyst hit rate on these rows.
    """
    empty = {"n_overrides": int(len(overrides)), "n_scored_obs": 0,
             "analyst_hit_rate": None, "model_hit_rate": None,
             "by_reason": [], "rows": []}
    if overrides.empty or panel.empty or "fwd_rel_ret_1q" not in panel.columns:
        return empty

    lab = panel.dropna(subset=["fwd_rel_ret_1q"])[["date", "ticker", "fwd_rel_ret_1q"]]
    obs_rows = []
    for _, ov in overrides.iterrows():
        w = lab[(lab["ticker"] == ov["ticker"])
                & (lab["date"] >= ov["date"]) & (lab["date"] <= ov["expires"])]
        for _, r in w.iterrows():
            rel = float(r["fwd_rel_ret_1q"])
            analyst_correct = (rel < 0) == (ov["direction"] == "more_risky")
            obs_rows.append({
                "ticker": ov["ticker"], "analyst": ov["analyst"],
                "direction": ov["direction"], "reason_code": ov["reason_code"],
                "quarter": pd.Timestamp(r["date"]).date().isoformat(),
                "rel_ret": round(rel, 4),
                "analyst_correct": bool(analyst_correct),
            })
    if not obs_rows:
        return empty

    obs = pd.DataFrame(obs_rows)
    by_reason = (obs.groupby("reason_code")
                    .agg(n_obs=("analyst_correct", "size"),
                         analyst_hit_rate=("analyst_correct", "mean"),
                         avg_rel_ret=("rel_ret", "mean"))
                    .reset_index())
    hit = float(obs["analyst_correct"].mean())
    logger.info("Override scoreboard: %d obs, analyst hit %.0f%% vs model %.0f%%",
                len(obs), hit * 100, (1 - hit) * 100)
    return {
        "n_overrides": int(len(overrides)),
        "n_scored_obs": int(len(obs)),
        "analyst_hit_rate": hit,
        "model_hit_rate": float(1 - hit),
        "by_reason": by_reason.round(4).to_dict("records"),
        "rows": obs_rows,
    }
