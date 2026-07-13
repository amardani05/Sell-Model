"""Quarterly rebalanced backtests of the sector neutral deciles.

Three equity curves, all stepping one quarter at a time over the panel's cross
sections and using each name's realized next quarter TOTAL return
(``fwd_ret_1q``):

  (a) **Equal weight universe (hold all)** — own every scored name, equal
      weight. This is the FAIR base for the screen: an equal weight small cap
      portfolio structurally beats a cap weighted benchmark, so measuring the
      screen against IJR would credit the model with the equal weight effect.
  (b) **Avoid worst decile** — hold everything except the worst sell decile,
      equal weight. Its value added is measured against (a): the delta is
      exactly what dropping the flagged decile contributed.
  (c) **IJR** — the cap weighted S&P 600 ETF, reported as market context only.

The long/short sleeve was removed deliberately: IMA is long only, and a 10 bps
cost assumption wildly understates real small cap borrow, so its Sharpe was an
invitation to objections rather than evidence. The concentrated picker question
("does the screen help a 20 name portfolio?") lives in ``simulate.py``.

Both sleeves are **delisting aware for free**: the panel's forward returns
already carry delisted names to ``config.DELISTING_TERMINAL_RETURN``, and the
data integrity gate has already excluded splice artifact windows. Transaction
cost = turnover x ``cost_bps``; turnover is reported.
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


def relative_metrics(strategy: BacktestResult, base: BacktestResult) -> dict:
    """Strategy minus base, quarter by quarter: the screen's actual value added.

    excess_cagr_vs_base   CAGR difference on the common quarters
    tracking_error        annualized std of the quarterly return differences
    ir_vs_base            annualized excess / tracking error
    hit_rate_vs_base      fraction of quarters the strategy beat the base
    """
    common = strategy.returns.index.intersection(base.returns.index)
    if len(common) < 2:
        return {}
    rs, rb = strategy.returns.loc[common], base.returns.loc[common]
    diff = rs - rb
    years = len(common) / ANN
    cagr_s = (1 + rs).prod() ** (1 / years) - 1
    cagr_b = (1 + rb).prod() ** (1 / years) - 1
    te = diff.std(ddof=1) * np.sqrt(ANN)
    return {
        "excess_cagr_vs_base": float(cagr_s - cagr_b),
        "tracking_error": float(te),
        "ir_vs_base": float((diff.mean() * ANN) / te) if te > 0 else np.nan,
        "hit_rate_vs_base": float((diff > 0).mean()),
        "n_quarters": int(len(common)),
    }


def _benchmark_quarterly(benchmark_px: pd.Series, dates: list[pd.Timestamp]) -> pd.Series:
    """Quarter over quarter benchmark returns aligned to rebalance dates."""
    if benchmark_px is None or benchmark_px.empty:
        return pd.Series(dtype=float)
    bpx = benchmark_px.reindex(benchmark_px.index.union(dates)).ffill().reindex(dates)
    return bpx.pct_change().shift(-1).iloc[:-1]  # return realized over (t, t+1)


def benchmark_result(benchmark_px: pd.Series, dates: list[pd.Timestamp],
                     name: str = "IJR (cap weighted S&P 600 ETF)") -> BacktestResult:
    """The benchmark itself as a sleeve, so its CAGR/Sharpe sit in the same table."""
    bench_q = _benchmark_quarterly(benchmark_px, dates).dropna()
    if bench_q.empty:
        return BacktestResult(name=name, returns=pd.Series(dtype=float),
                              equity=pd.Series(dtype=float))
    res = BacktestResult(name=name, returns=bench_q, equity=(1 + bench_q).cumprod())
    res.metrics = _metrics(bench_q)
    res.metrics["avg_turnover"] = np.nan  # not modeled for the ETF
    return res


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
def _run_long_only(panel: pd.DataFrame, decile_col: str, benchmark_px: pd.Series | None,
                   keep: "callable", name: str, cost_bps: float) -> BacktestResult:
    """Equal weight long only sleeve holding the names ``keep`` selects."""
    dates = sorted(panel["date"].unique())
    rets, turns, w_prev = [], [], pd.Series(dtype=float)

    for t in dates[:-1]:
        g = panel[(panel["date"] == t)].dropna(subset=["fwd_ret_1q", decile_col])
        held = g[keep(g[decile_col])]
        if held.empty:
            continue
        w = pd.Series(1.0 / len(held), index=held["ticker"].values)
        gross = float((w.values * held["fwd_ret_1q"].values).sum())
        to = _turnover(w_prev, w)
        cost = to * cost_bps / 1e4
        rets.append((pd.Timestamp(t), gross - cost))
        turns.append((pd.Timestamp(t), to))
        w_prev = w

    return _assemble(name, rets, turns, benchmark_px, dates)


def backtest_hold_all(panel: pd.DataFrame, decile_col: str, benchmark_px: pd.Series | None,
                      cost_bps: float = config.COST_BPS) -> BacktestResult:
    """Own every scored name, equal weight — the fair base for the screen."""
    return _run_long_only(panel, decile_col, benchmark_px,
                          keep=lambda d: d.notna(),
                          name="Equal weight universe (hold all)", cost_bps=cost_bps)


def backtest_long_only_avoid_worst(
    panel: pd.DataFrame, decile_col: str, benchmark_px: pd.Series | None,
    cost_bps: float = config.COST_BPS,
) -> BacktestResult:
    """Hold every name except the worst sell decile, equal weight."""
    n = config.N_DECILES
    return _run_long_only(panel, decile_col, benchmark_px,
                          keep=lambda d: d < n,
                          name="Avoid worst decile", cost_bps=cost_bps)


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


# =============================================================================
# Segmentation — every sub period stands alone
# =============================================================================
def segment_by_year(sleeves: dict[str, BacktestResult]) -> pd.DataFrame:
    """Compounded calendar year return per sleeve (independent windows)."""
    live = {k: r for k, r in sleeves.items()
            if not r.returns.empty and isinstance(r.returns.index, pd.DatetimeIndex)}
    if not live:
        return pd.DataFrame()
    rows = []
    years = sorted({d.year for res in live.values() for d in res.returns.index})
    for y in years:
        row: dict = {"year": int(y)}
        for key, res in live.items():
            r = res.returns[res.returns.index.year == y]
            row[key] = float((1 + r).prod() - 1) if len(r) else None
            row[f"{key}_n"] = int(len(r))
        rows.append(row)
    return pd.DataFrame(rows)


def segment_by_regime(sleeves: dict[str, BacktestResult], bench_q: pd.Series) -> pd.DataFrame:
    """Mean quarterly return per sleeve in benchmark up vs down quarters.

    A sell screen that only works when the market falls is a different product
    from one that works throughout — this split is how you find out which one
    you have.
    """
    if bench_q is None or bench_q.dropna().empty:
        return pd.DataFrame()
    b = bench_q.dropna()
    rows = []
    for regime, mask in [("benchmark up", b > 0), ("benchmark down", b <= 0)]:
        dates = b.index[mask]
        row: dict = {"regime": regime, "n_quarters": int(mask.sum())}
        for key, res in sleeves.items():
            r = res.returns.reindex(dates).dropna()
            row[key] = float(r.mean()) if len(r) else None
        row["benchmark"] = float(b[mask].mean())
        rows.append(row)
    return pd.DataFrame(rows)
