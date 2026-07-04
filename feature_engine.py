"""Factor computation, the point in time panel, and forward RELATIVE returns.

This is where the model's identity lives. Two jobs:

1. **Compute raw factors** at each quarterly cross section, using ONLY data
   dated <= the cross section date (no look ahead):
     * price factors (``mom_12_1``, ``reversal_1m``) — deep history, every date;
     * fundamental factors — yfinance gives ~4 5 quarters, lagged by a reporting
       delay, so they populate only the most recent cross sections. Missing ->
       NaN, dropped from the cross section by the model. NEVER faked.

2. **Build the panel** [date, ticker, gics_sector, <factors>, fwd_rel_ret_h].
   The label is the **sector relative** forward return:
       fwd_rel_ret_h = stock_fwd_ret_h - median(sector peers' fwd_ret_h)
   and it is **delisting aware**: a name that stops trading during the horizon
   is carried to ``config.DELISTING_TERMINAL_RETURN`` (= the strongest possible
   underperformer), never silently dropped.

yfinance fundamental field names vary by ticker, so every line item lookup goes
through :func:`get_field` with a list of aliases. Per ticker errors are
swallowed and logged.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

import config
from data_loader import RawBundle

logger = logging.getLogger(__name__)

# Fundamentals are knowable only after they are filed. Lag every quarterly
# statement by this many calendar days before it may inform a cross section.
REPORTING_LAG_DAYS: int = 60

PRICE_FACTORS = {"mom_12_1", "reversal_1m"}


# =============================================================================
# Robust yfinance field lookup (alias pattern)
# =============================================================================
def get_field(df: pd.DataFrame | None, names: list[str], col_idx: int = 0):
    """First non NaN value among ``names`` in column ``col_idx`` (most recent = 0)."""
    if df is None or df.empty or col_idx >= df.shape[1]:
        return None
    for name in names:
        if name in df.index:
            try:
                val = df.loc[name].iloc[col_idx]
            except Exception:  # noqa: BLE001
                continue
            if isinstance(val, pd.Series):
                val = val.iloc[0] if len(val) else None
            if val is not None and pd.notna(val):
                try:
                    return float(val)
                except (TypeError, ValueError):
                    continue
    return None


FIELDS = {
    "total_assets": ["Total Assets"],
    "total_liabilities": ["Total Liabilities Net Minority Interest", "Total Liab", "Total Liabilities"],
    "total_equity": ["Stockholders Equity", "Total Stockholder Equity", "Common Stock Equity"],
    "total_debt": ["Total Debt"],
    "long_term_debt": ["Long Term Debt"],
    "short_term_debt": ["Current Debt", "Short Long Term Debt"],
    "cash": ["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments", "Cash"],
    "shares": ["Ordinary Shares Number", "Share Issued", "Common Stock"],
    "revenue": ["Total Revenue", "Revenue", "Operating Revenue"],
    "gross_profit": ["Gross Profit"],
    "ebitda": ["EBITDA", "Normalized EBITDA"],
    "ebit": ["EBIT", "Operating Income"],
    "net_income": ["Net Income", "Net Income Common Stockholders"],
    "dep_amort": ["Reconciled Depreciation", "Depreciation And Amortization", "Depreciation"],
    "ocf": ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities",
            "Total Cash From Operating Activities"],
    "capex": ["Capital Expenditure", "Capital Expenditures", "Purchase Of PPE"],
}


def _col(df: pd.DataFrame | None, key: str, idx: int):
    return get_field(df, FIELDS[key], idx)


def _ttm(df: pd.DataFrame | None, key: str, start: int) -> float | None:
    """Sum of four consecutive quarters starting at column ``start`` (None if short)."""
    if df is None or df.empty or start + 4 > df.shape[1]:
        return None
    vals = [_col(df, key, start + j) for j in range(4)]
    if any(v is None for v in vals):
        return None
    return float(np.sum(vals))


# =============================================================================
# Per ticker fundamental factor time series (statement derived, price free)
# =============================================================================
def _fundamental_timeseries(bundle: RawBundle) -> pd.DataFrame:
    """Statement derived factors per ticker, indexed by the as of date.

    The as of date = quarter end + REPORTING_LAG_DAYS (when the print is public).
    Columns include the raw aggregates the panel needs for price based valuation
    ratios (net_income_ttm, ebitda_ttm, revenue_ttm, fcf_ttm, total_debt, cash,
    shares) plus the price free factors (roe, roa, margins, YoY trends, accruals).
    """
    fin = bundle.quarterly_financials
    bs = bundle.quarterly_balance_sheet
    cf = bundle.quarterly_cashflow
    # The financials frame defines the quarter columns (most recent first).
    if fin is None or fin.empty:
        return pd.DataFrame()
    quarter_ends = [pd.Timestamp(c) for c in fin.columns]
    n = len(quarter_ends)

    rows = []
    for q in range(n):
        # Need a trailing twelve month window starting at q.
        rev = _ttm(fin, "revenue", q)
        gp = _ttm(fin, "gross_profit", q)
        ni = _ttm(fin, "net_income", q)
        ebit = _ttm(fin, "ebit", q)
        da = _ttm(cf, "dep_amort", q)
        ebitda = _ttm(fin, "ebitda", q)
        if ebitda is None and ebit is not None and da is not None:
            ebitda = ebit + abs(da)
        ocf = _ttm(cf, "ocf", q)
        capex = _ttm(cf, "capex", q)
        fcf = (ocf - abs(capex)) if (ocf is not None and capex is not None) else None
        # Balance sheet levels at this quarter.
        assets = _col(bs, "total_assets", q)
        liab = _col(bs, "total_liabilities", q)
        equity = _col(bs, "total_equity", q)
        if equity is None and assets is not None and liab is not None:
            equity = assets - liab
        debt = _col(bs, "total_debt", q)
        if debt is None:
            ltd, std = _col(bs, "long_term_debt", q), _col(bs, "short_term_debt", q)
            debt = (ltd or 0) + (std or 0) if (ltd or std) else None
        cash = _col(bs, "cash", q)
        shares = _col(bs, "shares", q)

        def _safe(numer, denom):
            if numer is None or denom is None or denom == 0:
                return np.nan
            return numer / denom

        rows.append({
            "as_of": quarter_ends[q] + pd.Timedelta(days=REPORTING_LAG_DAYS),
            "quarter_end": quarter_ends[q],
            # aggregates the panel needs for price based ratios
            "net_income_ttm": ni if ni is not None else np.nan,
            "ebitda_ttm": ebitda if ebitda is not None else np.nan,
            "revenue_ttm": rev if rev is not None else np.nan,
            "fcf_ttm": fcf if fcf is not None else np.nan,
            "total_debt": debt if debt is not None else np.nan,
            "cash": cash if cash is not None else np.nan,
            "shares": shares if shares is not None else np.nan,
            "total_assets": assets if assets is not None else np.nan,
            # price free factors
            "roe": _safe(ni, equity),
            "roa": _safe(ni, assets),
            "gross_margin": _safe(gp, rev),
            "fcf_margin": _safe(fcf, rev),
            "accruals_ocf_ni": _safe(ocf, ni),
        })

    ts = pd.DataFrame(rows).set_index("as_of").sort_index()
    # YoY trends need the quarter 4 prior (rows are chronological after sort, so
    # 4 index positions back == one year). yfinance depth usually allows ~1 YoY.
    ts["roe_yoy"] = ts["roe"] - ts["roe"].shift(4)
    ts["gross_margin_yoy"] = ts["gross_margin"] - ts["gross_margin"].shift(4)
    ts["asset_growth_yoy"] = ts["total_assets"] / ts["total_assets"].shift(4) - 1.0
    ts["net_issuance_yoy"] = ts["shares"] / ts["shares"].shift(4) - 1.0
    return ts


# =============================================================================
# Price factors (vectorized over the full daily matrix)
# =============================================================================
def _price_factor_panels(prices: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Daily indexed wide panels for each price factor (data <= each date only)."""
    d21, d252 = 21, 252
    # 12 1 momentum: total return from t 252 to t 21 (skip the most recent month).
    mom = prices.shift(d21) / prices.shift(d252) - 1.0
    # short term reversal: the most recent ~1 month return.
    rev = prices / prices.shift(d21) - 1.0
    return {"mom_12_1": mom, "reversal_1m": rev}


def _quarter_end_dates(prices: pd.DataFrame) -> list[pd.Timestamp]:
    """Trading day quarter ends present in the price index."""
    idx = prices.index
    q = pd.Series(idx, index=idx).groupby([idx.year, idx.quarter]).last()
    return list(pd.to_datetime(q.values))


def _asof_sample(panel: pd.DataFrame, dates: list[pd.Timestamp]) -> pd.DataFrame:
    """Sample a daily wide panel at ``dates`` using last value <= date (ffill)."""
    return panel.reindex(panel.index.union(dates)).ffill().reindex(dates)


# =============================================================================
# Forward relative returns (delisting aware)
# =============================================================================
def _forward_returns(prices: pd.DataFrame, q_dates: list[pd.Timestamp], horizon_q: int) -> pd.DataFrame:
    """Wide [date x ticker] forward TOTAL return over ``horizon_q`` quarters.

    Delisting aware: a name that stops trading between t and the horizon end is
    set to ``config.DELISTING_TERMINAL_RETURN`` (carried to terminal value).
    A still living name without enough future data yet stays NaN.
    """
    horizon_days = horizon_q * config.TRADING_DAYS_PER_QUARTER
    px_q = _asof_sample(prices, q_dates)                       # price at each rebalance
    last_valid = prices.apply(lambda c: c.last_valid_index())  # per ticker
    dataset_end = prices.index.max()
    buffer = pd.Timedelta(days=15)
    idx = prices.index

    out = pd.DataFrame(index=q_dates, columns=prices.columns, dtype=float)
    for t in q_dates:
        pos = idx.searchsorted(t)
        tgt_pos = pos + horizon_days
        tgt_date = idx[tgt_pos] if tgt_pos < len(idx) else None
        p_now = px_q.loc[t]
        if tgt_date is not None:
            p_fut = prices.loc[tgt_date]
            ret = p_fut / p_now - 1.0
        else:
            ret = pd.Series(np.nan, index=prices.columns)
        # Delisting fill: name dead before horizon end and after t -> terminal.
        for tk in prices.columns:
            if pd.notna(ret[tk]):
                continue
            lv = last_valid[tk]
            if lv is None or pd.isna(p_now[tk]):
                continue
            horizon_end = tgt_date if tgt_date is not None else (t + pd.Timedelta(days=int(horizon_days * 1.5)))
            dead = lv < (dataset_end - buffer)          # stopped trading mid sample
            if dead and t < lv < horizon_end:
                ret[tk] = config.DELISTING_TERMINAL_RETURN
        out.loc[t] = ret
    return out


# =============================================================================
# Panel assembly
# =============================================================================
def build_panel(
    prices: pd.DataFrame,
    bundles: dict[str, RawBundle],
    membership: pd.DataFrame,
    short_interest: pd.Series | None = None,
    estimate_ts: dict[str, pd.DataFrame] | None = None,
) -> pd.DataFrame:
    """Assemble the long panel of factors + forward relative returns.

    membership: long frame [date, ticker, gics_sector] (point in time).
    Returns columns: date, ticker, gics_sector, <active factors>,
    short_pct_float, fwd_ret_<h>q, fwd_rel_ret_<h>q, delisted.
    """
    q_dates = _quarter_end_dates(prices)
    # Only score dates where at least the shortest horizon's future exists OR
    # we can fill via delisting; keep all and let labels be NaN where unknown.
    logger.info("Panel: %d quarter end cross sections, %d price tickers",
                len(q_dates), prices.shape[1])

    # --- price factors sampled at quarter ends ---
    pf = _price_factor_panels(prices)
    pf_q = {name: _asof_sample(panel, q_dates) for name, panel in pf.items()}

    # --- forward returns per horizon (delisting aware) ---
    fwd = {h: _forward_returns(prices, q_dates, h) for h in config.HORIZONS_Q}

    # --- fundamental factor time series per ticker ---
    fund_ts: dict[str, pd.DataFrame] = {}
    for tk, b in bundles.items():
        try:
            ts = _fundamental_timeseries(b)
            if not ts.empty:
                fund_ts[tk] = ts
        except Exception as exc:  # noqa: BLE001
            logger.debug("%s: fundamental timeseries failed: %s", tk, exc)

    # membership lookup: (date, ticker) -> sector
    mem = membership.copy()
    mem["date"] = pd.to_datetime(mem["date"]).dt.normalize()
    q_norm = [pd.Timestamp(d).normalize() for d in q_dates]
    mem = mem[mem["date"].isin(q_norm)]
    sector_lookup = mem.set_index(["date", "ticker"])["gics_sector"].to_dict()

    si = short_interest if short_interest is not None else pd.Series(dtype=float)
    price_free_fund = ["roe", "roa", "gross_margin", "fcf_margin", "accruals_ocf_ni",
                       "roe_yoy", "gross_margin_yoy", "asset_growth_yoy", "net_issuance_yoy"]

    records = []
    for t, t_norm in zip(q_dates, q_norm):
        members = mem.loc[mem["date"] == t_norm, "ticker"].tolist()
        if not members:
            continue
        for tk in members:
            if tk not in prices.columns:
                continue
            rec = {
                "date": t_norm,
                "ticker": tk,
                "gics_sector": sector_lookup.get((t_norm, tk), "Unknown"),
            }
            # price factors
            for name in pf_q:
                rec[name] = pf_q[name].at[t, tk] if tk in pf_q[name].columns else np.nan
            # fundamental factors as of t (lagged), with price based valuation ratios
            ts = fund_ts.get(tk)
            fr = None
            if ts is not None:
                avail = ts[ts.index <= t]
                if not avail.empty:
                    fr = avail.iloc[-1]
            for name in price_free_fund:
                rec[name] = float(fr[name]) if (fr is not None and pd.notna(fr.get(name))) else np.nan
            # price based valuation ratios (need as of price x shares)
            price_now = _asof_price(prices, t, tk)
            rec.update(_valuation_ratios(fr, price_now))
            # estimate factors (gated; NaN unless a deep loader supplied them)
            if config.USE_ESTIMATE_FACTORS and estimate_ts and tk in estimate_ts:
                ets = estimate_ts[tk]
                ea = ets[ets.index <= t]
                row = ea.iloc[-1] if not ea.empty else None
                for name in config.ESTIMATE_FACTORS:
                    rec[name] = float(row[name]) if (row is not None and name in row and pd.notna(row[name])) else np.nan
            # metadata
            rec["short_pct_float"] = float(si.get(tk, np.nan)) if len(si) else np.nan
            # labels
            delisted_flag = False
            for h in config.HORIZONS_Q:
                v = fwd[h].at[t, tk] if tk in fwd[h].columns else np.nan
                rec[f"fwd_ret_{h}q"] = v
                if pd.notna(v) and v == config.DELISTING_TERMINAL_RETURN:
                    delisted_flag = True
            rec["delisted"] = delisted_flag
            records.append(rec)

    panel = pd.DataFrame.from_records(records)
    if panel.empty:
        return panel

    # --- sector relative labels: stock fwd minus sector peer median ---
    for h in config.HORIZONS_Q:
        col = f"fwd_ret_{h}q"
        med = panel.groupby(["date", "gics_sector"])[col].transform("median")
        panel[f"fwd_rel_ret_{h}q"] = panel[col] - med

    logger.info("Panel built: %d rows, %d delisted carried labels",
                len(panel), int(panel["delisted"].sum()))
    return panel


# =============================================================================
# Sector neutralization  (the defining step of this model)
# =============================================================================
def _winsorize(s: pd.Series, pct: float) -> pd.Series:
    if s.notna().sum() < 3 or pct <= 0:
        return s
    lo, hi = s.quantile(pct), s.quantile(1 - pct)
    return s.clip(lo, hi)


def neutralize_factors(panel: pd.DataFrame, factors: list[str] | None = None) -> pd.DataFrame:
    """Add a direction aligned, SECTOR NEUTRAL column for every active factor.

    For each (date, gics_sector) cross section, each raw factor is winsorized
    and then z scored (or percentile ranked, per ``config.NEUTRALIZE_METHOD``)
    WITHIN the sector. The result is multiplied by the factor's red flag
    direction so that, for every factor, **larger => more expected sector relative
    underperformance**. The neutral columns are named ``<factor>__n``.

    Sectors with fewer than ``config.MIN_NAMES_PER_SECTOR`` names on a date are
    dropped from that cross section (ranks are meaningless on tiny groups).
    """
    factors = factors or [f for f in config.active_factors() if f in panel.columns]
    df = panel.copy()
    method = config.NEUTRALIZE_METHOD

    # Drop (date, sector) groups that are too small to rank.
    grp_sizes = df.groupby(["date", "gics_sector"])['ticker'].transform("size")
    too_small = grp_sizes < config.MIN_NAMES_PER_SECTOR
    if too_small.any():
        logger.info("Neutralize: dropping %d rows in sectors with < %d names",
                    int(too_small.sum()), config.MIN_NAMES_PER_SECTOR)
        df = df[~too_small].copy()

    def _neutral(group: pd.Series) -> pd.Series:
        g = _winsorize(group.astype(float), config.WINSORIZE_PCT)
        if method == "rank":
            out = g.rank(pct=True) - 0.5     # centered percentile in [-0.5, 0.5]
        else:
            mu, sd = g.mean(), g.std(ddof=0)
            out = (g - mu) / sd if (sd and np.isfinite(sd) and sd > 0) else g * 0.0
        return out

    gb = df.groupby(["date", "gics_sector"], group_keys=False)
    for f in factors:
        direction = config.RED_FLAG_DIRECTION.get(f, 1)
        df[f"{f}__n"] = gb[f].apply(_neutral) * direction
    return df


def _asof_price(prices: pd.DataFrame, t: pd.Timestamp, tk: str) -> float:
    if tk not in prices.columns:
        return np.nan
    s = prices[tk]
    s = s[s.index <= t].dropna()
    return float(s.iloc[-1]) if len(s) else np.nan


def _valuation_ratios(fr: pd.Series | None, price_now: float) -> dict:
    """Price based valuation factors from a fundamental row + the as of price."""
    out = {"pe_ratio": np.nan, "ev_to_ebitda": np.nan, "ps_ratio": np.nan, "fcf_yield": np.nan}
    if fr is None or not np.isfinite(price_now):
        return out
    shares = fr.get("shares")
    if shares is None or not np.isfinite(shares) or shares <= 0:
        return out
    mcap = price_now * shares
    ni = fr.get("net_income_ttm")
    rev = fr.get("revenue_ttm")
    ebitda = fr.get("ebitda_ttm")
    fcf = fr.get("fcf_ttm")
    debt = fr.get("total_debt") if np.isfinite(fr.get("total_debt", np.nan)) else 0.0
    cash = fr.get("cash") if np.isfinite(fr.get("cash", np.nan)) else 0.0
    ev = mcap + debt - cash
    if ni is not None and np.isfinite(ni) and ni > 0:
        out["pe_ratio"] = mcap / ni
    if ebitda is not None and np.isfinite(ebitda) and ebitda > 0:
        out["ev_to_ebitda"] = ev / ebitda
    if rev is not None and np.isfinite(rev) and rev > 0:
        out["ps_ratio"] = mcap / rev
    if fcf is not None and np.isfinite(fcf) and ev > 0:
        out["fcf_yield"] = fcf / ev
    return out
