"""Dump every pipeline table to ``webapp/public/data/*.json`` + ``meta.json``.

The React dashboard reads these at runtime and builds its Plotly figures from the
raw data tables (react plotly), so the contract here is just: one JSON document
per logical table, NaN -> null, dates -> ISO strings. Run is idempotent.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

import numpy as np
import pandas as pd

import config

logger = logging.getLogger(__name__)

DATA_DIR = config.WEBAPP_PUBLIC / "data"


def _ensure() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _records(df: pd.DataFrame) -> list[dict]:
    if df is None or df.empty:
        return []
    out = df.replace({np.nan: None})
    return json.loads(out.to_json(orient="records", date_format="iso"))


def _write(payload, stem: str) -> None:
    path = DATA_DIR / f"{stem}.json"
    path.write_text(json.dumps(payload, default=str))
    logger.debug("wrote %s (%d bytes)", path.name, path.stat().st_size)


def _round(v, nd=4):
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return None
    return round(float(v), nd)


# =============================================================================
# Tables
# =============================================================================
def export_scores(latest: pd.DataFrame, score_col: str, decile_col: str) -> None:
    """Latest scored cross section: ranked sell candidates with factor detail.

    Carries the torpedo columns too, so the dashboard can plot the sector neutral
    sell decile against the absolute torpedo percentile on the same rows.
    """
    factor_n = [f"{f}__n" for f in config.active_factors() if f"{f}__n" in latest.columns]
    torp = [c for c in ["torpedo_score", "torpedo_pct", "torpedo_tier"] if c in latest.columns]
    keep = ["date", "ticker", "gics_sector", "index_name", score_col, decile_col, "n_factors_used",
            "short_pct_float"] + torp + factor_n
    df = latest[[c for c in keep if c in latest.columns]].copy()
    df = df.rename(columns={score_col: "score", decile_col: "decile"})
    df["sell_rank"] = df["score"].rank(ascending=False, method="first")
    df = df.sort_values("score", ascending=False)
    _write(_records(df), "scores")


def export_torpedo(latest: pd.DataFrame, score_col: str, decile_col: str) -> None:
    """Latest cross section ranked by absolute torpedo risk, plus tier counts."""
    if "torpedo_pct" not in latest.columns:
        _write({"names": [], "tier_counts": [], "tier_colors": config.TORPEDO_TIER_COLORS,
                "tier_order": [t[2] for t in config.TORPEDO_TIERS]}, "torpedo")
        return
    df = latest.rename(columns={score_col: "score", decile_col: "decile"})
    keep = ["ticker", "gics_sector", "index_name", "torpedo_score", "torpedo_pct", "torpedo_tier",
            "decile", "score", "short_pct_float"]
    cols = [c for c in keep if c in df.columns]
    df = df[cols].dropna(subset=["torpedo_pct"]).sort_values("torpedo_pct", ascending=False)
    tier_counts = (df.groupby("torpedo_tier").size().reset_index(name="n")
                   if "torpedo_tier" in df.columns else pd.DataFrame())
    _write({
        "names": _records(df),
        "tier_counts": _records(tier_counts),
        "tier_colors": config.TORPEDO_TIER_COLORS,
        "tier_order": [t[2] for t in config.TORPEDO_TIERS],
    }, "torpedo")


def export_sector_deciles(latest: pd.DataFrame, decile_col: str) -> None:
    """Per sector decile composition + the worst decile names in each sector."""
    df = latest.dropna(subset=[decile_col]).copy()
    counts = (df.groupby(["gics_sector", decile_col]).size()
                .reset_index(name="n").rename(columns={decile_col: "decile"}))
    worst = df[df[decile_col] == config.N_DECILES]
    worst_names = (worst.groupby("gics_sector")["ticker"]
                        .apply(lambda s: sorted(s.tolist())).reset_index()
                        .rename(columns={"ticker": "worst_decile_names"}))
    payload = {
        "counts": _records(counts),
        "worst_decile_names": {r["gics_sector"]: r["worst_decile_names"]
                               for r in worst_names.to_dict("records")},
        "n_deciles": config.N_DECILES,
        "sectors": sorted(df["gics_sector"].unique().tolist()),
    }
    _write(payload, "sector_deciles")


def export_factor_ic(factor_ic: pd.DataFrame, horizon_q: int) -> None:
    _write({"horizon_q": horizon_q, "factors": _records(factor_ic)}, "factor_ic")


def export_validation(ic_summaries: dict, decile_summaries: dict,
                      calibration: pd.DataFrame, comparison: pd.DataFrame,
                      promotion: dict | None, event_study: pd.DataFrame,
                      eras: pd.DataFrame, era_ic: pd.DataFrame,
                      yearly_ic: pd.DataFrame) -> None:
    """ic_summaries / decile_summaries keyed by horizon_q -> validate dataclasses."""
    ic_payload = {}
    for h, s in ic_summaries.items():
        ic_payload[str(h)] = {
            "mean_ic": s.mean_ic, "t_stat": s.t_stat, "ir": s.ir,
            "hit_rate": s.hit_rate, "n_periods": s.n_periods,
            "series": _records(s.series),
        }
    dec_payload = {}
    for h, d in decile_summaries.items():
        dec_payload[str(h)] = {
            "per_decile_mean": _records(d.per_decile_mean),
            "spread_mean": d.spread_mean, "spread_tstat": d.spread_tstat,
            "monotonicity_rho": d.monotonicity_rho,
            "spread_series": _records(d.spread_series),
        }
    _write({
        "ic": ic_payload,
        "deciles": dec_payload,
        "calibration": _records(calibration),
        "model_comparison": _records(comparison),
        "promotion": promotion,
        "event_study": _records(event_study),
        "eras": _records(eras),
        "era_ic": _records(era_ic),
        "yearly_ic": _records(yearly_ic),
        "label_winsor_pct": config.LABEL_WINSOR_PCT,
        "era_min_avg_factors": config.ERA_MIN_AVG_FACTORS,
    }, "validation")


def export_backtest(results: dict, seg_year: pd.DataFrame, seg_regime: pd.DataFrame) -> None:
    """results: name -> BacktestResult, plus the segmentation tables."""
    payload = {"sleeves": {}, "segments": {"by_year": _records(seg_year),
                                           "by_regime": _records(seg_regime)}}
    for key, res in results.items():
        eq = res.equity
        beq = res.benchmark_equity
        payload["sleeves"][key] = {
            "name": res.name,
            "metrics": {k: (None if (isinstance(v, float) and not np.isfinite(v)) else v)
                        for k, v in res.metrics.items()},
            "curve": [{"date": pd.Timestamp(d).isoformat(),
                       "strategy": float(v),
                       "benchmark": (float(beq.get(d)) if (beq is not None and d in beq.index and pd.notna(beq.get(d))) else None)}
                      for d, v in eq.items()],
            "returns": [{"date": pd.Timestamp(d).isoformat(), "ret": float(v)}
                        for d, v in res.returns.items()],
            "turnover": [{"date": pd.Timestamp(d).isoformat(), "turnover": float(v)}
                         for d, v in res.turnover.items()],
        }
    _write(payload, "backtest")


def export_mc(mc: dict) -> None:
    """The IMA Monte Carlo simulation output (already JSON shaped)."""
    _write(mc or {}, "mc_sim")


def export_exclusions(exclusions: pd.DataFrame) -> None:
    """The data integrity report: every label the splice gate refused to use."""
    df = exclusions.copy() if exclusions is not None else pd.DataFrame()
    payload = {
        "n_labels_excluded": int(len(df)),
        "n_tickers": int(df["ticker"].nunique()) if len(df) else 0,
        "reasons": df["reason"].value_counts().to_dict() if len(df) else {},
        "rows": _records(df.sort_values(["ticker", "date"]) if len(df) else df),
    }
    _write(payload, "exclusions")


def export_drilldown(panel: pd.DataFrame, latest: pd.DataFrame,
                     score_col: str, decile_col: str) -> None:
    """Per name factor decomposition for the drill down panel.

    For every name in the latest cross section: raw factor values, the direction
    aligned sector neutral z (``__n``), the within sector percentile of that z
    (0-100, higher = stronger red flag), the prior quarter z (QoQ change), the
    prior quarter score/decile, and the as of date of the fundamentals used.
    """
    factors = [f for f in config.active_factors() if f"{f}__n" in latest.columns]
    dates = sorted(panel["date"].unique())
    latest_date = dates[-1]
    prev_date = dates[-2] if len(dates) > 1 else None
    prev = panel[panel["date"] == prev_date] if prev_date is not None else pd.DataFrame()
    prev_by_tk = prev.set_index("ticker") if not prev.empty else pd.DataFrame()

    df = latest.copy()
    # within sector percentile of the aligned z, per factor (red flag intensity)
    for f in factors:
        col = f"{f}__n"
        df[f"{f}__pct"] = (df.groupby("gics_sector")[col]
                             .rank(pct=True, na_option="keep") * 100.0)

    names: dict = {}
    for _, r in df.iterrows():
        tk = r["ticker"]
        pr = prev_by_tk.loc[tk] if (not prev_by_tk.empty and tk in prev_by_tk.index) else None
        if isinstance(pr, pd.DataFrame):  # duplicated ticker safety
            pr = pr.iloc[0]
        fund_as_of = r.get("fund_as_of")
        entry = {
            "sector": r["gics_sector"],
            "index_name": r.get("index_name") or "",
            "score": _round(r.get(score_col)),
            "decile": _round(r.get(decile_col), 0),
            "prev_score": _round(pr.get(score_col)) if pr is not None else None,
            "prev_decile": _round(pr.get(decile_col), 0) if pr is not None else None,
            "n_factors_used": int(r.get("n_factors_used") or 0),
            "fund_as_of": (pd.Timestamp(fund_as_of).date().isoformat()
                           if pd.notna(fund_as_of) else None) if "fund_as_of" in df.columns else None,
            "torpedo_pct": _round(r.get("torpedo_pct"), 1),
            "torpedo_tier": r.get("torpedo_tier"),
            "short_pct_float": _round(r.get("short_pct_float")),
            "factors": {},
        }
        for f in factors:
            raw, z, pct = r.get(f), r.get(f"{f}__n"), r.get(f"{f}__pct")
            prev_z = pr.get(f"{f}__n") if pr is not None else None
            if pd.isna(raw) and pd.isna(z):
                entry["factors"][f] = None   # not populated for this name
                continue
            entry["factors"][f] = {
                "raw": _round(raw, 6),
                "z": _round(z),
                "pct": _round(pct, 1),
                "prev_z": _round(prev_z) if prev_z is not None and pd.notna(prev_z) else None,
            }
        names[tk] = entry

    _write({
        "as_of": pd.Timestamp(latest_date).date().isoformat(),
        "prev_date": pd.Timestamp(prev_date).date().isoformat() if prev_date is not None else None,
        "factor_order": factors,
        "names": names,
    }, "drilldown")


def export_overrides(ov_active: pd.DataFrame, ov_scoreboard: dict) -> None:
    """Active analyst overrides + the quarterly scoreboard (annotations only)."""
    from overrides import REASON_CODES
    act = ov_active.copy() if ov_active is not None else pd.DataFrame()
    if not act.empty:
        act["date"] = pd.to_datetime(act["date"]).dt.date.astype(str)
        act["expires"] = pd.to_datetime(act["expires"]).dt.date.astype(str)
    _write({
        "active": _records(act),
        "scoreboard": ov_scoreboard or {},
        "reason_codes": REASON_CODES,
    }, "overrides")


def export_transitions(panel: pd.DataFrame, decile_col: str) -> None:
    """Decile persistence: the transition matrix + this quarter's flag churn."""
    d = panel.dropna(subset=[decile_col])[["date", "ticker", decile_col]].copy()
    d[decile_col] = d[decile_col].astype(int)
    dates = sorted(d["date"].unique())
    n = config.N_DECILES

    counts = np.zeros((n, n), dtype=int)
    for a, b in zip(dates[:-1], dates[1:]):
        da = d[d["date"] == a].set_index("ticker")[decile_col]
        db = d[d["date"] == b].set_index("ticker")[decile_col]
        common = da.index.intersection(db.index)
        for tk in common:
            counts[da[tk] - 1, db[tk] - 1] += 1
    row_sums = counts.sum(axis=1, keepdims=True)
    with np.errstate(invalid="ignore", divide="ignore"):
        probs = np.where(row_sums > 0, counts / row_sums, 0.0)

    # churn between the two most recent cross sections
    new_flagged, exited = [], []
    if len(dates) >= 2:
        prev = d[d["date"] == dates[-2]].set_index("ticker")[decile_col]
        cur_panel = panel[panel["date"] == dates[-1]]
        cur = cur_panel.set_index("ticker")
        for tk, dec in cur[decile_col].dropna().items():
            p = prev.get(tk)
            if dec >= n - 1 and (p is None or p < n - 1):
                new_flagged.append({"ticker": tk, "sector": cur.at[tk, "gics_sector"],
                                    "decile": int(dec),
                                    "prev_decile": int(p) if p is not None else None})
            elif p is not None and p >= n - 1 and dec < n - 1:
                exited.append({"ticker": tk, "sector": cur.at[tk, "gics_sector"],
                               "decile": int(dec), "prev_decile": int(p)})

    _write({
        "n_deciles": n,
        "n_date_pairs": max(0, len(dates) - 1),
        "counts": counts.tolist(),
        "row_prob": np.round(probs, 4).tolist(),
        "new_flagged": sorted(new_flagged, key=lambda r: -r["decile"]),
        "exited": sorted(exited, key=lambda r: r["ticker"]),
        "latest_date": pd.Timestamp(dates[-1]).date().isoformat() if dates else None,
        "prev_date": pd.Timestamp(dates[-2]).date().isoformat() if len(dates) > 1 else None,
    }, "transitions")


def export_meta(*, universe_size, n_sectors, horizon_q, source, learned_enabled,
                default_score, membership_is_pit, diagnostics, n_cross_sections,
                cost_bps, panel_rows, n_delisted, exclusions_summary=None,
                index_counts=None) -> None:
    payload = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "model": "Relative Sell Model (sector neutral relative underperformance ranking)",
        "universe_size": int(universe_size),
        "n_sectors": int(n_sectors),
        "n_cross_sections": int(n_cross_sections),
        "panel_rows": int(panel_rows),
        "n_delisted_carried": int(n_delisted),
        "horizon_q": int(horizon_q),
        "horizons_available": list(config.HORIZONS_Q),
        "benchmark": config.BENCHMARK_TICKER,
        "source": source,
        "cost_bps": cost_bps,
        "neutralize_method": config.NEUTRALIZE_METHOD,
        "n_factors": len(config.active_factors()),
        "factor_groups": config.FACTOR_GROUPS,
        "learned_weights_enabled": bool(learned_enabled),
        "default_score": default_score,
        "membership_point_in_time": bool(membership_is_pit),
        "index_counts": index_counts or {},
        "use_estimate_factors": config.USE_ESTIMATE_FACTORS,
        "diagnostics": diagnostics,
        "exclusions_summary": exclusions_summary or {},
        "mc_portfolio_size": config.MC_PORTFOLIO_SIZE,
        "mc_n_trials": config.MC_N_TRIALS,
        "sector_colors": _SECTOR_COLORS,
        "torpedo_tier_colors": config.TORPEDO_TIER_COLORS,
        "torpedo_tier_order": [t[2] for t in config.TORPEDO_TIERS],
        "n_torpedo_features": len(config.TORPEDO_FEATURES),
    }
    (config.WEBAPP_PUBLIC / "meta.json").write_text(json.dumps(payload, indent=2, default=str))
    logger.info("Wrote meta.json")


_SECTOR_COLORS = {
    "Information Technology": "#4e79a7", "Health Care": "#59a14f",
    "Financials": "#9c755f", "Consumer Discretionary": "#edc948",
    "Industrials": "#76b7b2", "Materials": "#b07aa1",
    "Consumer Staples": "#ff9da7", "Energy": "#e15759",
    "Utilities": "#bab0ac", "Real Estate": "#86bcb6",
    "Communication Services": "#f28e2b", "Unknown": "#cccccc",
}


def export_all(*, panel, latest, score_col, decile_col, factor_ic, horizon_q,
               ic_summaries, decile_summaries, calibration, comparison, promotion,
               event_study, eras, era_ic, yearly_ic,
               backtests, seg_year, seg_regime, mc, exclusions,
               ov_active=None, ov_scoreboard=None, meta_kwargs=None) -> None:
    _ensure()
    # Stamp each name with its index membership (S&P 600 vs 400) for the UI flag.
    try:
        from universe import index_membership_map
        imap = index_membership_map()
        latest = latest.copy()
        latest["index_name"] = latest["ticker"].map(imap).fillna("")
        counts = latest["index_name"].value_counts().to_dict()
        meta_kwargs = {**meta_kwargs, "index_counts": {k: int(v) for k, v in counts.items() if k}}
    except Exception as exc:  # noqa: BLE001
        logger.warning("index membership flag unavailable: %s", exc)
        latest = latest.copy()
        latest["index_name"] = ""
    export_scores(latest, score_col, decile_col)
    export_sector_deciles(latest, decile_col)
    export_torpedo(latest, score_col, decile_col)
    export_factor_ic(factor_ic, horizon_q)
    export_validation(ic_summaries, decile_summaries, calibration, comparison,
                      promotion, event_study, eras, era_ic, yearly_ic)
    export_backtest(backtests, seg_year, seg_regime)
    export_mc(mc)
    export_exclusions(exclusions)
    export_drilldown(panel, latest, score_col, decile_col)
    export_transitions(panel, decile_col)
    export_overrides(ov_active, ov_scoreboard)
    export_meta(**meta_kwargs)
    logger.info("webapp_export: wrote scores/sector_deciles/torpedo/factor_ic/validation/"
                "backtest/mc_sim/exclusions/drilldown/transitions/overrides + meta")
