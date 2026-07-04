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
    keep = ["date", "ticker", "gics_sector", score_col, decile_col, "n_factors_used",
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
    keep = ["ticker", "gics_sector", "torpedo_score", "torpedo_pct", "torpedo_tier",
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
                      calibration: pd.DataFrame, comparison: pd.DataFrame) -> None:
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
    }, "validation")


def export_backtest(results: dict) -> None:
    """results: name -> BacktestResult."""
    payload = {}
    for key, res in results.items():
        eq = res.equity
        beq = res.benchmark_equity
        payload[key] = {
            "name": res.name,
            "metrics": res.metrics,
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


def export_meta(*, universe_size, n_sectors, horizon_q, source, learned_enabled,
                default_score, membership_is_pit, diagnostics, n_cross_sections,
                cost_bps, panel_rows, n_delisted) -> None:
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
        "use_estimate_factors": config.USE_ESTIMATE_FACTORS,
        "diagnostics": diagnostics,
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


def export_all(*, latest, score_col, decile_col, factor_ic, horizon_q,
               ic_summaries, decile_summaries, calibration, comparison,
               backtests, meta_kwargs) -> None:
    _ensure()
    export_scores(latest, score_col, decile_col)
    export_sector_deciles(latest, decile_col)
    export_torpedo(latest, score_col, decile_col)
    export_factor_ic(factor_ic, horizon_q)
    export_validation(ic_summaries, decile_summaries, calibration, comparison)
    export_backtest(backtests)
    export_meta(**meta_kwargs)
    logger.info("webapp_export: wrote scores/sector_deciles/torpedo/factor_ic/validation/backtest + meta")
