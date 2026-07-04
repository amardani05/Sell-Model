"""Quarterly rebalanced backtests of the sector neutral deciles.

Two sleeves, both stepping one quarter at a time over the panel's cross sections
and using each name's realized next quarter TOTAL return (``fwd_ret_1q``):

  (a) long only "AVOID THE WORST sector neutral decile" vs IJR — hold every name
      except those in the worst sell decile, equal weight, and compare to the
      benchmark;
  (b) sector neutral LONG/SHORT — long the best decile, short the worst decile,
      dollar neutral, aggregated across sectors.

Both are **delisting aware for free**: the panel's forward returns already carry
delisted names to ``config.DELISTING_TERMINAL_RETURN``, so a delisted short is a
realized win and a delisted long a realized loss — exactly the survivorship
payoff Ben's model never saw. Transaction cost = turnover x ``cost_bps``;
turnover is reported.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

import config

logger = logging.getLogger(__name__)
ANN = 4  # quarters per year


@dataclass
class BacktestResult:
    name: str
    returns: pd.Series                     # per quarter net return, indexed by date
    equity: pd.Series                      # cumulative growth of $1
    benchmark_returns: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    benchmark_equity: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    turnover: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    metrics: dict = field(default_factory=dict)


# =============================================================================
# Metrics
# =============================================================================
def _metrics(returns: pd.Series, benchmark: pd.Series | None = None) -> dict:
    r = returns.dropna()
    if r.empty:
        return {}
    growth = (1 + r).prod()
    years = len(r) / ANN
    cagr = growth ** (1 / years) - 1 if years > 0 and growth > 0 else np.nan
    vol = r.std(ddof=1) * np.sqrt(ANN)
    sharpe = (r.mean() * ANN) / vol if vol > 0 else np.nan
    equity = (1 + r).cumprod()
    max_dd = float((equity / equity.cummax() - 1).min())
    out = {
        "cagr": float(cagr), "vol": float(vol), "sharpe": float(sharpe),
        "max_drawdown": max_dd, "n_quarters": int(len(r)),
        "total_return": float(growth - 1),
    }
    if benchmark is not None and not benchmark.empty:
        b = benchmark.reindex(r.index).dropna()
        ra = r.reindex(b.index)
        out["hit_rate_vs_bench"] = float((ra > b).mean())
        out["excess_cagr"] = out["cagr"] - (((1 + b).prod()) ** (1 / (len(b) / ANN)) - 1)
    return out


def _benchmark_quarterly(benchmark_px: pd.Series, dates: list[pd.Timestamp]) -> pd.Series:
    """Quarter over quarter benchmark returns aligned to rebalance dates."""
    if benchmark_px is None or benchmark_px.empty:
        return pd.Series(dtype=float)
    bpx = benchmark_px.reindex(benchmark_px.index.union(dates)).ffill().reindex(dates)
    return bpx.pct_change().shift(-1).iloc[:-1]  # return realized over (t, t+1)


# =============================================================================
# Turnover
# =============================================================================
def _turnover(w_prev: pd.Series, w_now: pd.Series) -> float:
    allnames = w_prev.index.union(w_now.index)
    a = w_prev.reindex(allnames).fillna(0.0)
    b = w_now.reindex(allnames).fillna(0.0)
    return 0.5 * float((a - b).abs().sum())


# =============================================================================
# Strategies
# =============================================================================
def backtest_long_only_avoid_worst(
    panel: pd.DataFrame, decile_col: str, benchmark_px: pd.Series,
    cost_bps: float = config.COST_BPS,
) -> BacktestResult:
    """Hold every name except the worst sell decile, equal weight, vs IJR."""
    n = config.N_DECILES
    dates = sorted(panel["date"].unique())
    rets, turns, w_prev = [], [], pd.Series(dtype=float)

    for t in dates[:-1]:
        g = panel[(panel["date"] == t)].dropna(subset=["fwd_ret_1q", decile_col])
        held = g[g[decile_col] < n]
        if held.empty:
            continue
        w = pd.Series(1.0 / len(held), index=held["ticker"].values)
        gross = float((w.values * held["fwd_ret_1q"].values).sum())
        to = _turnover(w_prev, w)
        cost = to * cost_bps / 1e4
        rets.append((pd.Timestamp(t), gross - cost))
        turns.append((pd.Timestamp(t), to))
        w_prev = w

    return _assemble("Long only: avoid worst decile", rets, turns, benchmark_px, dates)


def backtest_long_short(
    panel: pd.DataFrame, decile_col: str,
    cost_bps: float = config.COST_BPS, gross: float = config.LONG_SHORT_GROSS,
) -> BacktestResult:
    """Sector neutral L/S: long best decile, short worst decile, dollar neutral."""
    n = config.N_DECILES
    dates = sorted(panel["date"].unique())
    rets, turns, w_prev = [], [], pd.Series(dtype=float)

    for t in dates[:-1]:
        g = panel[(panel["date"] == t)].dropna(subset=["fwd_ret_1q", decile_col])
        longs = g[g[decile_col] == 1]
        shorts = g[g[decile_col] == n]
        if longs.empty or shorts.empty:
            continue
        wl = pd.Series(gross / len(longs), index=longs["ticker"].values)
        ws = pd.Series(-gross / len(shorts), index=shorts["ticker"].values)
        w = pd.concat([wl, ws])
        r = (float((wl.values * longs["fwd_ret_1q"].values).sum())
             + float((ws.values * shorts["fwd_ret_1q"].values).sum()))
        to = _turnover(w_prev, w)
        cost = to * cost_bps / 1e4
        rets.append((pd.Timestamp(t), r - cost))
        turns.append((pd.Timestamp(t), to))
        w_prev = w

    return _assemble("Sector neutral long/short", rets, turns, None, dates)


def _assemble(name, rets, turns, benchmark_px, dates) -> BacktestResult:
    if not rets:
        return BacktestResult(name=name, returns=pd.Series(dtype=float), equity=pd.Series(dtype=float))
    r = pd.Series({d: v for d, v in rets}).sort_index()
    to = pd.Series({d: v for d, v in turns}).sort_index()
    equity = (1 + r).cumprod()
    bench_q = _benchmark_quarterly(benchmark_px, dates) if benchmark_px is not None else pd.Series(dtype=float)
    bench_q = bench_q.reindex(r.index) if not bench_q.empty else bench_q
    bench_eq = (1 + bench_q).cumprod() if not bench_q.empty else pd.Series(dtype=float)
    res = BacktestResult(name=name, returns=r, equity=equity,
                         benchmark_returns=bench_q, benchmark_equity=bench_eq, turnover=to)
    res.metrics = _metrics(r, bench_q if not bench_q.empty else None)
    res.metrics["avg_turnover"] = float(to.mean())
    logger.info("Backtest %-32s CAGR=%.1f%% Sharpe=%.2f maxDD=%.1f%% turnover=%.0f%%",
                name, res.metrics.get("cagr", np.nan) * 100, res.metrics.get("sharpe", np.nan),
                res.metrics.get("max_drawdown", np.nan) * 100, res.metrics["avg_turnover"] * 100)
    return res
